class AssumptionOverrides(InputModel):
    regional_populations: dict[str, int] | None = None
    penetration_rate: float | None = Field(default=None, ge=0, le=1)
    annual_spend_per_customer_usd: float | None = Field(default=None, ge=0)
    core_audience_value_usd: float | None = Field(default=None, ge=0)
