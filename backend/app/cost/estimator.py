"""
AWS cost estimation. Clearly labelled as an ESTIMATE, never presented as
guaranteed billing. Tries the live AWS Price List API first (accurate, but
slow/complex and not available for every SKU); falls back to a small
reference table of well-known on-demand Linux prices for common instance
families when the live API call fails or is unavailable. The reference table
is only used for the cost preview — it is never used to constrain which
instance types can be provisioned (that list is always fetched dynamically
from EC2's DescribeInstanceTypes, see tools/aws_tool.py).
"""
from __future__ import annotations

from dataclasses import dataclass

# Approximate USD/hour on-demand Linux reference prices (us-east-1), used only
# as a fallback display estimate when the live Pricing API is unavailable.
_REFERENCE_HOURLY_USD = {
    "t3.nano": 0.0052, "t3.micro": 0.0104, "t3.small": 0.0208, "t3.medium": 0.0416,
    "t3.large": 0.0832, "t3.xlarge": 0.1664, "t3.2xlarge": 0.3328,
    "m5.large": 0.096, "m5.xlarge": 0.192, "m5.2xlarge": 0.384,
    "c5.large": 0.085, "c5.xlarge": 0.17,
    "r5.large": 0.126, "r5.xlarge": 0.252,
}

EBS_GP3_USD_PER_GB_MONTH = 0.08


@dataclass
class CostEstimate:
    monthly_usd: float | None
    hourly_usd: float | None
    is_estimate: bool
    source: str
    note: str


def estimate_ec2_monthly_cost(aws_tool, instance_type: str, region: str, ebs_gb: int = 0) -> CostEstimate:
    hourly = None
    source = "reference_table"
    try:
        pricing = aws_tool.client("pricing")
        # AWS Pricing API only operates against us-east-1 / ap-south-1 endpoints
        # and requires verbose filter matching; kept intentionally minimal here.
        region_names = {"us-east-1": "US East (N. Virginia)"}
        location = region_names.get(region)
        if location:
            resp = pricing.get_products(
                ServiceCode="AmazonEC2",
                Filters=[
                    {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                    {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                    {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
                    {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
                    {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
                    {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
                ],
                MaxResults=1,
            )
            if resp.get("PriceList"):
                import json
                product = json.loads(resp["PriceList"][0])
                terms = product.get("terms", {}).get("OnDemand", {})
                for term in terms.values():
                    for dim in term.get("priceDimensions", {}).values():
                        hourly = float(dim["pricePerUnit"]["USD"])
                        source = "aws_pricing_api"
                        break
    except Exception:  # noqa: BLE001
        hourly = None

    if hourly is None:
        hourly = _REFERENCE_HOURLY_USD.get(instance_type)

    if hourly is None:
        return CostEstimate(None, None, True, "unavailable", f"No pricing reference available for '{instance_type}'.")

    monthly_compute = hourly * 24 * 30
    monthly_storage = ebs_gb * EBS_GP3_USD_PER_GB_MONTH
    monthly = round(monthly_compute + monthly_storage, 2)
    return CostEstimate(
        monthly_usd=monthly, hourly_usd=hourly, is_estimate=True, source=source,
        note="This is an ESTIMATE based on on-demand Linux pricing and does not include data transfer, "
             "taxes, support plans, or non-default configuration. Actual billing may differ.",
    )
