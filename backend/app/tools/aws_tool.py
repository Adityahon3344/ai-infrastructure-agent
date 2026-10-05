"""Real AWS integration via boto3. Every "catalog" of instance types, AMIs,
regions, VPCs etc. is discovered dynamically through the AWS API — nothing is
hard-coded (no fixed t3.micro/t3.small lists). Only a safe, explicit allowlist
of read-only describe/list calls plus a small set of validated mutating calls
(create instance, terminate instance, etc.) are exposed; everything else is
rejected before it reaches boto3.
"""
from __future__ import annotations

from typing import Any, Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

# Read-only "describe/list" actions considered LOW risk and safe to call for
# discovery/inspection purposes without approval.
SAFE_READONLY_ACTIONS = {
    "ec2": [
        "describe_instances", "describe_instance_types", "describe_images",
        "describe_regions", "describe_availability_zones", "describe_vpcs",
        "describe_subnets", "describe_security_groups", "describe_volumes",
        "describe_key_pairs", "describe_snapshots",
    ],
    "elbv2": ["describe_load_balancers", "describe_target_groups"],
    "rds": ["describe_db_instances", "describe_db_snapshots"],
    "s3": ["list_buckets"],
    "ecs": ["list_clusters", "list_services", "list_tasks"],
    "eks": ["list_clusters", "describe_cluster"],
    "lambda": ["list_functions"],
    "route53": ["list_hosted_zones", "list_resource_record_sets"],
    "cloudwatch": ["list_metrics", "get_metric_statistics", "describe_alarms"],
    "sts": ["get_caller_identity"],
    "pricing": ["get_products"],
}


class AWSPermissionError(Exception):
    pass


class AWSTool:
    def __init__(self, credentials: Optional[dict] = None, region: Optional[str] = None):
        self.credentials = credentials or {}
        self.region = region or self.credentials.get("region_name") or settings.aws_default_region
        if self.region not in settings.aws_allowed_region_list:
            raise AWSPermissionError(
                f"Region '{self.region}' is not in the allowed region list: {settings.aws_allowed_region_list}"
            )
        session_kwargs = {k: v for k, v in {
            "aws_access_key_id": self.credentials.get("aws_access_key_id") or settings.aws_access_key_id or None,
            "aws_secret_access_key": self.credentials.get("aws_secret_access_key") or settings.aws_secret_access_key or None,
            "aws_session_token": self.credentials.get("aws_session_token") or None,
            "region_name": self.region,
        }.items() if v}
        self.session = boto3.session.Session(**session_kwargs)
        self._clients: dict[str, Any] = {}

    def client(self, service: str):
        if service not in self._clients:
            self._clients[service] = self.session.client(service, config=BotoConfig(retries={"max_attempts": 3}))
        return self._clients[service]

    def call_readonly(self, service: str, action: str, **kwargs) -> Any:
        if service not in SAFE_READONLY_ACTIONS or action not in SAFE_READONLY_ACTIONS[service]:
            raise AWSPermissionError(f"'{service}.{action}' is not in the read-only allowlist")
        client = self.client(service)
        method = getattr(client, action)
        return method(**kwargs)

    # ---- Convenience wrappers used by the catalog / discovery layer ----

    def get_caller_identity(self) -> dict:
        sts = self.client("sts")
        identity = sts.get_caller_identity()
        return {"account": identity.get("Account"), "arn": identity.get("Arn"), "user_id": identity.get("UserId")}

    def list_regions(self) -> list[str]:
        ec2 = self.client("ec2")
        resp = ec2.describe_regions(AllRegions=False)
        return sorted(r["RegionName"] for r in resp.get("Regions", []))

    def list_availability_zones(self) -> list[str]:
        ec2 = self.client("ec2")
        resp = ec2.describe_availability_zones()
        return sorted(z["ZoneName"] for z in resp.get("AvailabilityZones", []))

    def list_instance_types(self, *, min_vcpu: int | None = None, max_price_tier: str | None = None) -> list[dict]:
        """Dynamically discovers instance types available in this account/region
        (no hard-coded list). Optionally filters by vCPU count."""
        ec2 = self.client("ec2")
        paginator = ec2.get_paginator("describe_instance_types")
        types: list[dict] = []
        filters = []
        if min_vcpu:
            filters.append({"Name": "vcpu-info.default-vcpus", "Values": [str(min_vcpu)]})
        for page in paginator.paginate(Filters=filters or []):
            for it in page.get("InstanceTypes", []):
                types.append({
                    "instance_type": it["InstanceType"],
                    "vcpus": it.get("VCpuInfo", {}).get("DefaultVCpus"),
                    "memory_mib": it.get("MemoryInfo", {}).get("SizeInMiB"),
                    "architectures": it.get("ProcessorInfo", {}).get("SupportedArchitectures", []),
                    "current_generation": it.get("CurrentGeneration", False),
                    "free_tier_eligible": it.get("FreeTierEligible", False),
                    "network_performance": it.get("NetworkInfo", {}).get("NetworkPerformance"),
                })
        types.sort(key=lambda t: (t["vcpus"] or 0, t["memory_mib"] or 0))
        return types

    def list_amis(self, *, owners: list[str] | None = None, name_filter: str | None = None) -> list[dict]:
        ec2 = self.client("ec2")
        kwargs: dict = {"Owners": owners or ["amazon"]}
        if name_filter:
            kwargs["Filters"] = [{"Name": "name", "Values": [f"*{name_filter}*"]}]
        resp = ec2.describe_images(**kwargs)
        images = resp.get("Images", [])
        images.sort(key=lambda i: i.get("CreationDate", ""), reverse=True)
        return [
            {"image_id": i["ImageId"], "name": i.get("Name"), "description": i.get("Description"),
             "architecture": i.get("Architecture"), "creation_date": i.get("CreationDate")}
            for i in images[:50]
        ]

    def list_vpcs(self) -> list[dict]:
        ec2 = self.client("ec2")
        resp = ec2.describe_vpcs()
        return [{"vpc_id": v["VpcId"], "cidr": v.get("CidrBlock"), "is_default": v.get("IsDefault"),
                 "tags": {t["Key"]: t["Value"] for t in v.get("Tags", [])}} for v in resp.get("Vpcs", [])]

    def list_subnets(self, vpc_id: str | None = None) -> list[dict]:
        ec2 = self.client("ec2")
        kwargs = {"Filters": [{"Name": "vpc-id", "Values": [vpc_id]}]} if vpc_id else {}
        resp = ec2.describe_subnets(**kwargs)
        return [{"subnet_id": s["SubnetId"], "vpc_id": s["VpcId"], "cidr": s.get("CidrBlock"),
                 "availability_zone": s.get("AvailabilityZone")} for s in resp.get("Subnets", [])]

    def list_security_groups(self, vpc_id: str | None = None) -> list[dict]:
        ec2 = self.client("ec2")
        kwargs = {"Filters": [{"Name": "vpc-id", "Values": [vpc_id]}]} if vpc_id else {}
        resp = ec2.describe_security_groups(**kwargs)
        return [{"group_id": g["GroupId"], "name": g.get("GroupName"), "vpc_id": g.get("VpcId"),
                 "description": g.get("Description")} for g in resp.get("SecurityGroups", [])]

    def list_instances(self, *, tags: dict | None = None) -> list[dict]:
        ec2 = self.client("ec2")
        filters = []
        for k, v in (tags or {}).items():
            filters.append({"Name": f"tag:{k}", "Values": [v]})
        resp = ec2.describe_instances(Filters=filters or [])
        instances = []
        for reservation in resp.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                instances.append({
                    "instance_id": inst["InstanceId"],
                    "state": inst.get("State", {}).get("Name"),
                    "instance_type": inst.get("InstanceType"),
                    "public_ip": inst.get("PublicIpAddress"),
                    "private_ip": inst.get("PrivateIpAddress"),
                    "tags": {t["Key"]: t["Value"] for t in inst.get("Tags", [])},
                })
        return instances

    def list_s3_buckets(self) -> list[dict]:
        s3 = self.client("s3")
        resp = s3.list_buckets()
        return [{"name": b["Name"], "creation_date": b["CreationDate"].isoformat()} for b in resp.get("Buckets", [])]

    def list_rds_instances(self) -> list[dict]:
        rds = self.client("rds")
        resp = rds.describe_db_instances()
        return [{"identifier": d["DBInstanceIdentifier"], "engine": d.get("Engine"),
                 "status": d.get("DBInstanceStatus"), "instance_class": d.get("DBInstanceClass")}
                for d in resp.get("DBInstances", [])]

    # ---- Mutating actions (MEDIUM/HIGH risk, always go through validation+approval upstream) ----

    def run_instances(self, *, image_id: str, instance_type: str, key_name: str | None,
                       subnet_id: str | None, security_group_ids: list[str] | None,
                       tags: dict, min_count: int = 1, max_count: int = 1) -> dict:
        ec2 = self.client("ec2")
        kwargs: dict = {
            "ImageId": image_id,
            "InstanceType": instance_type,
            "MinCount": min_count,
            "MaxCount": max_count,
            "TagSpecifications": [{"ResourceType": "instance", "Tags": [{"Key": k, "Value": v} for k, v in tags.items()]}],
        }
        if key_name:
            kwargs["KeyName"] = key_name
        if subnet_id:
            kwargs["SubnetId"] = subnet_id
        if security_group_ids:
            kwargs["SecurityGroupIds"] = security_group_ids
        resp = ec2.run_instances(**kwargs)
        return {"instance_ids": [i["InstanceId"] for i in resp.get("Instances", [])]}

    def terminate_instances(self, instance_ids: list[str]) -> dict:
        ec2 = self.client("ec2")
        resp = ec2.terminate_instances(InstanceIds=instance_ids)
        return {"terminating": [c["InstanceId"] for c in resp.get("TerminatingInstances", [])]}

    def create_vpc(self, cidr_block: str, tags: dict) -> dict:
        ec2 = self.client("ec2")
        resp = ec2.create_vpc(CidrBlock=cidr_block, TagSpecifications=[
            {"ResourceType": "vpc", "Tags": [{"Key": k, "Value": v} for k, v in tags.items()]}
        ])
        return {"vpc_id": resp["Vpc"]["VpcId"]}
