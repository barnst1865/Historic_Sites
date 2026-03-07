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
    "NC": {
        "adapter": "arcgis",
        "name": "North Carolina SHPO Historic Resources",
        "endpoint": (
            "https://gis2.ncdcr.gov/dncrgis/rest/services/"
            "NCHPO_Public/NCHPO_Historic_Resources_CNC/MapServer/0/query"
        ),
        "field_map": {
            "name": ["Site_Name"],
            "address": [],
            "city": [],
            "county": ["County"],
            "state_record_id": ["Site_ID"],
            "date_constructed": [],
            "nris_refnum": [],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register", "National Register"],
        "designating_authority": "North Carolina SHPO",
        "active": True,
    },
    "MA": {
        "adapter": "arcgis",
        "name": "Massachusetts Historic Commission Inventory",
        "endpoint": (
            "http://arcgisserver.digital.mass.gov/arcgisserver/rest/services/"
            "AGOL/MHC_Inventory/FeatureServer/1/query"
        ),
        "field_map": {
            "name": ["COMMON_NAM", "HISTORIC_N"],
            "address": ["ADDRESS"],
            "city": ["TOWN_NAME"],
            "county": [],
            "state_record_id": ["MHCN"],
            "date_constructed": ["CONSTRUCTI"],
            "nris_refnum": [],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register"],
        "designating_authority": "Massachusetts Historical Commission",
        "active": True,
    },
    "FL": {
        "adapter": "arcgis",
        "name": "Florida Master Site File - Historical Structures",
        "endpoint": (
            "https://services.arcgis.com/2HXAtOKdBRSMj8is/arcgis/rest/services/"
            "NRHistoricStructures/FeatureServer/0/query"
        ),
        "field_map": {
            "name": ["SITENAME"],
            "address": ["ADDRESS"],
            "city": [],
            "county": [],
            "state_record_id": ["SITEID"],
            "date_constructed": ["YEARBUILT"],
            "nris_refnum": [],
            "date_listed": ["D_NRLISTED"],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register"],
        "designating_authority": "Florida SHPO",
        "active": True,
    },
    "ID": {
        "adapter": "arcgis",
        "name": "Idaho NRHP Sites",
        "endpoint": (
            "https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/"
            "jG8BM/FeatureServer/0/query"
        ),
        "field_map": {
            "name": ["f3"],
            "address": ["f4"],
            "city": ["f6"],
            "county": ["f5"],
            "state_record_id": ["f2"],
            "date_constructed": [],
            "nris_refnum": ["NR_REF"],
            "date_listed": ["f8"],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["National Register"],
        "designating_authority": "Idaho SHPO",
        "active": True,
    },
    "MT": {
        "adapter": "arcgis",
        "name": "Montana NRHP Properties",
        "endpoint": (
            "https://services.arcgis.com/qnjIrwR8z5Izc0ij/arcgis/rest/services/"
            "National_Register_Historic_Properties/FeatureServer/4/query"
        ),
        "field_map": {
            "name": ["Name"],
            "address": ["Street_Add"],
            "city": ["CITY"],
            "county": ["COUNTY"],
            "state_record_id": ["SITE_ID"],
            "date_constructed": [],
            "nris_refnum": ["NR_Referen"],
            "date_listed": ["Listing_Da"],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["National Register"],
        "designating_authority": "Montana SHPO",
        "active": True,
    },
    "WV": {
        "adapter": "arcgis",
        "name": "West Virginia SHPO Architectural Survey",
        "endpoint": (
            "https://services.wvgis.wvu.edu/arcgis/rest/services/"
            "Society/wv_SHPO_public/FeatureServer/0/query"
        ),
        "field_map": {
            "name": ["HistName", "CommonName"],
            "address": ["Addr"],
            "city": ["Town"],
            "county": ["County"],
            "state_record_id": ["Site_ID"],
            "date_constructed": ["DateConst"],
            "nris_refnum": [],
        },
        "page_size": 2000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register"],
        "designating_authority": "West Virginia SHPO",
        "active": True,
    },
}
