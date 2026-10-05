"""
Uses moto (a real AWS API simulator, not a hand-rolled mock) to prove that
instance-type/AMI/VPC discovery genuinely calls the AWS API surface and
returns dynamically discovered data rather than a hard-coded list.
"""
import boto3
import pytest
from moto import mock_aws

from app.tools.aws_tool import AWSTool, AWSPermissionError


@mock_aws
def test_dynamic_instance_type_discovery_returns_many_types():
    tool = AWSTool({"aws_access_key_id": "testing", "aws_secret_access_key": "testing", "region_name": "us-east-1"})
    types = tool.list_instance_types()
    # moto's simulated EC2 API exposes a large real instance-type catalog —
    # if this passed with a suspiciously short list we'd suspect hard-coding.
    assert len(types) > 50
    type_names = {t["instance_type"] for t in types}
    assert "t3.micro" in type_names
    assert "m5.large" in type_names


@mock_aws
def test_dynamic_vpc_and_subnet_discovery():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]
    ec2.create_subnet(VpcId=vpc["VpcId"], CidrBlock="10.0.1.0/24")

    tool = AWSTool({"aws_access_key_id": "testing", "aws_secret_access_key": "testing", "region_name": "us-east-1"})
    vpcs = tool.list_vpcs()
    assert any(v["vpc_id"] == vpc["VpcId"] for v in vpcs)

    subnets = tool.list_subnets(vpc["VpcId"])
    assert len(subnets) == 1


@mock_aws
def test_run_and_terminate_instance_lifecycle():
    tool = AWSTool({"aws_access_key_id": "testing", "aws_secret_access_key": "testing", "region_name": "us-east-1"})
    amis = tool.list_amis(owners=["amazon"])
    # moto ships a set of fake AMIs by default
    image_id = amis[0]["image_id"] if amis else "ami-12345678"

    result = tool.run_instances(image_id=image_id, instance_type="t3.micro", key_name=None, subnet_id=None, security_group_ids=None, tags={"Name": "test"})
    assert len(result["instance_ids"]) == 1

    instances = tool.list_instances()
    assert any(i["instance_id"] == result["instance_ids"][0] for i in instances)

    terminated = tool.terminate_instances(result["instance_ids"])
    assert result["instance_ids"][0] in terminated["terminating"]


def test_region_allowlist_enforced():
    with pytest.raises(AWSPermissionError):
        AWSTool({"aws_access_key_id": "testing", "aws_secret_access_key": "testing", "region_name": "not-a-real-region"})


@mock_aws
def test_readonly_allowlist_blocks_unlisted_action():
    tool = AWSTool({"aws_access_key_id": "testing", "aws_secret_access_key": "testing", "region_name": "us-east-1"})
    with pytest.raises(AWSPermissionError):
        tool.call_readonly("ec2", "run_instances")  # mutating action must not be reachable via the read-only path
