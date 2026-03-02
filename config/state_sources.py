"""
State SHPO data source registry.

Maps state codes to adapter configuration for ingesting state-level
historic preservation data. Each entry specifies the adapter type,
endpoint URL, field mappings, and pagination settings.

Field maps use lists of aliases (tried in order) to handle varying
ArcGIS field names across states — same pattern as arcgis_client._get_attr().
"""

STATE_SOURCES = {
    "IN": {
        "adapter": "arcgis",
        "name": "Indiana SHPO Historic Structures",
        "endpoint": (
            "https://gisdata.in.gov/server/rest/services/"
            "Hosted/IDNR_Historic_Structures/FeatureServer/0/query"
        ),
        "field_map": {
            "name": ["historicname"],
            "address": [],
            "city": [],
            "county": [],
            "state_record_id": ["shaard_id"],
            "date_constructed": [],
            "nris_refnum": [],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register"],
        "designating_authority": "Indiana SHPO",
        "active": True,
    },
    "MO": {
        "adapter": "arcgis",
        "name": "Missouri SHPO Historic Sites",
        "endpoint": (
            "https://gis.dnr.mo.gov/server/rest/services/"
            "cultural/historic_districts_and_sites/MapServer/0/query"
        ),
        "field_map": {
            "name": ["HST_NAME"],
            "alternate_name": ["OTHR_NAME"],
            "address": ["PADDRESS"],
            "city": ["PLOCALNAME"],
            "county": [],
            "state_record_id": ["SHPO_NUMBE"],
            "date_listed": ["DATE_LIST"],
            "nris_refnum": [],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register", "National Register"],
        "designating_authority": "Missouri SHPO",
        "active": True,
    },
    "UT": {
        "adapter": "arcgis",
        "name": "Utah SHPO Historic Buildings",
        "endpoint": (
            "https://shpo.utah.gov/server/rest/services/"
            "Hosted/Historic_Utah_Buildings/FeatureServer/0/query"
        ),
        "field_map": {
            "name": ["propertyname", "historicpropertyname"],
            "address_parts": {
                "number": ["housenumber"],
                "direction": ["streetdirection"],
                "street": ["streetname"],
            },
            "city": ["cityname"],
            "county": ["countyname"],
            "state_record_id": ["pr_id", "id_text"],
            "date_constructed": ["constructionyear1"],
            "nris_refnum": ["nrisnumber"],
            "date_listed": ["nrlisteddate"],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register"],
        "designating_authority": "Utah SHPO",
        "active": True,
    },
}
