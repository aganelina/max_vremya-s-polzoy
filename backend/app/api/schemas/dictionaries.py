from app.api.schemas.base import CamelModel
from app.api.schemas.common import Dict


class Dictionaries(CamelModel):
    universities: list[Dict]
    districts: list[Dict]
