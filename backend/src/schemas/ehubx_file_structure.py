"""
Pydantic models for techs.yaml file structure in EHubX
"""

import re
from typing import Optional, List, Union, Literal
from pydantic import BaseModel, Field, field_validator, model_serializer

NUMERIC_PREFIX_PATTERN = r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?(?:.*)$"


class EHubxBaseModel(BaseModel):
    """Base model that omits optional zero or None values during serialization."""

    @model_serializer(mode="wrap")
    def _omit_optional_zero_or_none(self, handler):
        data = handler(self)
        if not isinstance(data, dict):
            return data

        filtered = {}
        for key, value in data.items():
            field = type(self).model_fields.get(key)
            if field and not field.is_required() and (value is None or value == 0 or value == 0.0):
                continue
            filtered[key] = value

        return filtered


def _validate_numeric_prefix_value(value: Optional[Union[str, float]], field_name: str) -> Optional[Union[str, float]]:
    if value is None:
        return None

    if isinstance(value, str):
        if not re.match(NUMERIC_PREFIX_PATTERN, value):
            raise ValueError(f"{field_name} must start with a numeric value")
        return value

    return value


# ============================================================================
# Shared/Common Models
# ============================================================================


class TechParams(EHubxBaseModel):
    """Base technology parameters common to all technologies"""
    lifetime: str = Field(
        ...,
        pattern=NUMERIC_PREFIX_PATTERN,
        description="Lifetime of technology from installation to EOL in format '%d YR' (e.g., '25 YR')"
    )
    unit_cap_min: Optional[Union[str, float]] = Field(
        default=0.0,
        description="Minimal capacity that must be installed [CAP]"
    )
    introduced: Optional[Union[int, float, str]] = Field(
        default=None,
        description="Year the technology is introduced / becomes available"
    )
    trl: Optional[Union[int, float, List[List[int]]]] = Field(
        default=None,
        description="Technology Readiness Level (TRL) [-]"
    )

    @field_validator("unit_cap_min")
    @classmethod
    def validate_unit_cap_min(cls, value: Optional[Union[str, float]]) -> Optional[Union[str, float]]:
        return _validate_numeric_prefix_value(value, "unit_cap_min")


class CostParams(EHubxBaseModel):
    """Cost parameters for technologies"""
    interest_rate: Optional[Union[str, float]] = Field(
        default=None,
        description="Interest rate for this technology [-]"
    )
    one_time_capex: Optional[Union[str, float]] = Field(
        default=0.0,
        description="Fixed CAPEX cost [CHF]"
    )
    capex_per_cap: Optional[Union[str, float]] = Field(
        default=0.0,
        description="CAPEX cost per capacity [CHF/CAP]"
    )
    one_time_opex: Optional[Union[str, float]] = Field(
        default=0.0,
        description="Fixed OPEX cost [CHF]"
    )
    opex_per_cap: Optional[Union[str, float]] = Field(
        default=0.0,
        description="OPEX cost per capacity [CHF/CAP]"
    )
    opex_per_energy: Optional[Union[str, float]] = Field(
        default=0.0,
        description="OPEX cost per output energy (for conversion techs) [CHF/ec_out_main]"
    )

    @field_validator(
        "interest_rate",
        "one_time_capex",
        "capex_per_cap",
        "one_time_opex",
        "opex_per_cap",
        "opex_per_energy",
    )
    @classmethod
    def validate_cost_numeric_prefix_fields(
        cls,
        value: Optional[Union[str, float]],
        info,
    ) -> Optional[Union[str, float]]:
        return _validate_numeric_prefix_value(value, info.field_name)


class EmissionParams(EHubxBaseModel):
    """Emission parameters for technologies"""
    co2_per_cap: Optional[Union[str, float]] = Field(
        default=0.0,
        description="Embodied CO2 per installed capacity [kg/CAP]"
    )
    # manually added fields for embedded carbon under different scenarios, with LCA unit (e.g., "100 kg CO2 / CAP"), maybe to remove later if not needed
    ssp2_ndc: Optional[Union[str, float]] = Field(
        default=None,
        description="Embedded carbon under SSP2-NDC scenario with LCA unit [value unit]"
    )
    ssp2_pkbudg1000: Optional[Union[str, float]] = Field(
        default=None,
        description="Embedded carbon under SSP2-PkBudg1000 scenario with LCA unit [value unit]"
    )

    @field_validator("co2_per_cap", "ssp2_ndc", "ssp2_pkbudg1000")
    @classmethod
    def validate_co2_per_cap(cls, value: Optional[Union[str, float]]) -> Optional[Union[str, float]]:
        return _validate_numeric_prefix_value(value, "co2_per_cap")


class StorageParams(EHubxBaseModel):
    """Parameters for storage technologies"""
    ec: str = Field(..., description="ID of EC that is storable in this technology")
    in_eff: Optional[float] = Field(default=1, description="Efficiency of storage input [-]")
    out_eff: Optional[float] = Field(default=1, description="Efficiency of storage output [-]")
    charge_max: Optional[float] = Field(default=1, description="Maximal relative charging power [1/h]")
    discharge_max: Optional[float] = Field(default=1, description="Maximal relative discharging power [1/h]")
    soc_min: Optional[float] = Field(default=0, description="Minimal stage of charge [-]")
    soc_max: Optional[float] = Field(default=1, description="Maximal stage of charge [-]")
    standby_loss: Optional[float] = Field(default=0, description="Standby loss per timestep [1/h]")


class ConversionInput(EHubxBaseModel):
    """Input energy carrier for conversion technologies"""
    in_id: str = Field(..., description="ID of input EC or input EC group")
    in_part: Optional[Union[str, float]] = Field(default=None, description="Input part as fraction or with units [ec_in]")


class ConversionOutput(EHubxBaseModel):
    """Output energy carrier for conversion technologies"""
    ec_id: str = Field(..., description="ID of output EC")
    out_eff: Union[float, List[List[float]], str] = Field(
        ...,
        description="Output efficiency as value, [[year, eff], ...], or path to CSV file [ec_out / ec_in_main]"
    )


class ConversionParams(EHubxBaseModel):
    """Parameters for conversion technologies"""
    in_ecs: List[ConversionInput] = Field(..., description="List of input energy carriers")
    main_in_ec: Optional[str] = Field(default=None, description="ID of main input EC")
    out_ecs: List[ConversionOutput] = Field(..., description="List of output energy carriers")
    main_out_ec: Optional[str] = Field(default=None, description="ID of main output EC")


class SolarParams(EHubxBaseModel):
    """Parameters for solar technologies"""
    curtail_max_rel: Optional[float] = Field(default=1, description="Fraction of solar power that can be curtailed [-]")


class ATESECs(EHubxBaseModel):
    """Energy carriers for ATES technology"""
    elec: str = Field(..., description="EC for electricity consumption of well pumps")
    heat: str = Field(..., description="EC for heating energy from warm wells")
    cool: str = Field(..., description="EC for cooling energy from cold wells")


class ATESParams(EHubxBaseModel):
    """Parameters for ATES (Aquifer Thermal Energy Storage) technologies"""
    ecs: ATESECs = Field(..., description="Energy carriers for ATES")
    density_fluid: Optional[float] = Field(default=None, description="Density of stored fluid [kg/m^3]")
    specific_heat_capacity_fluid: Optional[float] = Field(
        default=None,
        description="Specific heat capacity of fluid [kWh/(kg*K)]"
    )
    well_radius: Optional[float] = Field(default=None, description="Radius of a well [m]")
    well_pair_area_calc_method: Optional[str] = Field(
        default="smallest rectangle",
        description="Calculation method for well pair area ('two circles' or 'smallest rectangle')"
    )
    elec_per_flow_heat: Optional[float] = Field(default=0, description="Electricity per warm volume flow [kWh/m^3]")
    elec_per_flow_cool: Optional[float] = Field(default=0, description="Electricity per cold volume flow [kWh/m^3]")


class EBMParams(EHubxBaseModel):
    """Parameters for Electricity-Based Mobility (EBM) technologies"""
    ec: str = Field(..., description="ID of EC that powers EBM vehicles")
    storage_cap: float = Field(..., description="Storage capacity of single EBM vehicle [ec]")
    in_eff: Optional[float] = Field(default=1, description="Efficiency of storage input [-]")
    out_eff: Optional[float] = Field(default=1, description="Efficiency of storage output [-]")
    standby_loss: Optional[float] = Field(default=0, description="Standby loss per timestep [1/h]")
    soc_min: Optional[float] = Field(default=0, description="Minimal stage of charge [-]")
    soc_max: Optional[float] = Field(default=1, description="Maximal stage of charge [-]")
    charge_max: Optional[float] = Field(default=None, description="Maximal charging power [ec/h]")
    discharge_max: Optional[float] = Field(default=None, description="Maximal discharging power [ec/h]")
    discharge_controllability: Optional[float] = Field(default=1, description="Discharge controllability factor [-]")


class CouplingParams(EHubxBaseModel):
    """Parameters for coupled technologies"""
    main_tech_id: str = Field(..., description="ID of main technology")
    cap_factor: float = Field(..., description="Capacity factor relative to main tech [CAP_sub/CAP_main]")


class HeatPumpECs(EHubxBaseModel):
    """Energy carriers for heat pump technology"""
    elec: str = Field(..., description="EC ID for electricity")
    heat_in: str = Field(..., description="EC ID for heat input in heating mode")
    heat_out: str = Field(..., description="EC ID for heat output in heating mode")
    cool_in: str = Field(..., description="EC ID for cooling input in cooling mode")
    cool_out: str = Field(..., description="EC ID for cooling output in cooling mode")


class HeatPumpParams(EHubxBaseModel):
    """Parameters for heat pump technologies"""
    ecs: HeatPumpECs = Field(..., description="Energy carriers for heat pump")
    cop_factor: Optional[float] = Field(default=0.5, description="COP factor for Carnot efficiency calculation [-]")


# ============================================================================
# Technology Type Models
# ============================================================================


class BaseTechnology(EHubxBaseModel):
    """Base model for all technologies"""
    tech_id: str = Field(..., description="Unique identifier for technology")
    type: Optional[str] = Field(default=None, description="Technology type")
    tech_params: TechParams = Field(..., description="Technology parameters")
    costs: Optional[CostParams] = Field(default=None, description="Cost parameters")
    emissions: Optional[EmissionParams] = Field(default=None, description="Emission parameters")

    class Config:
        extra = "allow"  # Allow extra fields for type-specific params


class StorageTechnology(BaseTechnology):
    """Model for storage technologies"""
    type: Literal["storage"] = "storage"
    storage_params: StorageParams = Field(..., description="Storage-specific parameters")


class ConversionTechnology(BaseTechnology):
    """Model for conversion technologies"""
    type: Literal["conversion"] = "conversion"
    conversion_params: ConversionParams = Field(..., description="Conversion-specific parameters")


class SolarTechnology(BaseTechnology):
    """Model for solar technologies"""
    type: Literal["solar"] = "solar"
    conversion_params: ConversionParams = Field(..., description="Conversion parameters for solar")
    solar_params: Optional[SolarParams] = Field(default=None, description="Solar-specific parameters")


class ATESTechnology(BaseTechnology):
    """Model for ATES (Aquifer Thermal Energy Storage) technologies"""
    type: Literal["ates"] = "ates"
    ates_params: ATESParams = Field(..., description="ATES-specific parameters")


class EBMTechnology(BaseTechnology):
    """Model for Electricity-Based Mobility (EBM) technologies"""
    type: Literal["ebm"] = "ebm"
    ebm_params: EBMParams = Field(..., description="EBM-specific parameters")


class CoupledTechnology(BaseTechnology):
    """Model for coupled technologies"""
    coupling_params: CouplingParams = Field(..., description="Coupling parameters")


class HeatPumpTechnology(BaseTechnology):
    """Model for heat pump technologies"""
    type: Literal["heatpump"] = "heatpump"
    heatpump_params: HeatPumpParams = Field(..., description="Heat pump-specific parameters")


# ============================================================================
# Root Model
# ============================================================================


class TechsConfig(EHubxBaseModel):
    """Root model for techs.yaml configuration"""
    techs: List[Union[
        StorageTechnology,
        ConversionTechnology,
        SolarTechnology,
        ATESTechnology,
        EBMTechnology,
        HeatPumpTechnology,
        CoupledTechnology,
        BaseTechnology  # Fallback for unknown types
    ]] = Field(default_factory=list, description="List of technologies")

    class Config:
        validate_assignment = True
        arbitrary_types_allowed = True
