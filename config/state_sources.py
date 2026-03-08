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
    "TX": {
        "adapter": "arcgis",
        "name": "Texas Historical Commission - Historic Properties",
        "endpoint": (
            "https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/"
            "Historic_Resources/FeatureServer/1/query"
        ),
        "field_map": {
            "name": ["Resource", "Alt_Name"],
            "address": ["Address"],
            "city": ["City"],
            "county": ["County"],
            "state_record_id": ["Prop_Num"],
            "date_constructed": ["Period"],
            "nris_refnum": [],
            "date_listed": ["NR_Date"],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register", "National Register"],
        "designating_authority": "Texas Historical Commission",
        "active": True,
    },
    "TN": {
        "adapter": "arcgis",
        "name": "Tennessee State Historic Sites",
        "endpoint": (
            "https://services5.arcgis.com/bPacKTm9cauMXVfn/arcgis/rest/services/"
            "Tennessee_State_Historic_Sites/FeatureServer/0/query"
        ),
        "field_map": {
            "name": ["Name"],
            "address": ["Address"],
            "city": [],
            "county": [],
            "state_record_id": [],
            "date_constructed": ["YearBuilt"],
            "nris_refnum": [],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register"],
        "designating_authority": "Tennessee Historical Commission",
        "active": True,
    },
    "AL": {
        "adapter": "arcgis",
        "name": "Alabama Architectural Survey Files",
        "endpoint": (
            "https://services2.arcgis.com/XBn0Kai3hQ20FeCo/arcgis/rest/services/"
            "AHC_Architectural_Survey_Files_Public_View/FeatureServer/0/query"
        ),
        "field_map": {
            "name": ["Prop_Name"],
            "address": ["Str_Add"],
            "city": ["City"],
            "county": [],
            "state_record_id": [],
            "date_constructed": ["Constr_Date"],
            "nris_refnum": [],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register"],
        "designating_authority": "Alabama Historical Commission",
        "active": True,
    },
    "AL_NR": {
        "adapter": "arcgis",
        "state_code": "AL",
        "name": "Alabama National Register Files",
        "endpoint": (
            "https://services2.arcgis.com/XBn0Kai3hQ20FeCo/arcgis/rest/services/"
            "AHC_National_Register_Files_Public_View/FeatureServer/0/query"
        ),
        "field_map": {
            "name": ["RESNAME"],
            "address": [],
            "city": [],
            "county": [],
            "state_record_id": ["CR_ID"],
            "nris_refnum": [],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["National Register"],
        "designating_authority": "Alabama Historical Commission",
        "active": True,
    },
    "RI": {
        "adapter": "arcgis",
        "name": "Rhode Island Historic Sites",
        "endpoint": (
            "https://services2.arcgis.com/S8zZg9pg23JUEexQ/arcgis/rest/services/"
            "CULT_Historic_Sites_spf/FeatureServer/0/query"
        ),
        "field_map": {
            "name": ["NAME"],
            "address": [],
            "city": ["TOWN"],
            "county": [],
            "state_record_id": ["CODE"],
            "nris_refnum": [],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register"],
        "designating_authority": "Rhode Island SHPO",
        "active": True,
    },
    # --- Texas GDB downloads from atlas.thc.texas.gov ---
    "TX_NR": {
        "adapter": "gdb",
        "state_code": "TX",
        "name": "Texas NR Properties (Atlas GDB)",
        "gdb_path": "manual-data/Texas/NationalRegisterProperties.gdb",
        "layer": "NationalRegisterPT",
        "field_map": {
            "name": ["RESNAME"],
            "address": ["ADDRESS"],
            "city": ["CITY"],
            "county": ["COUNTY"],
            "state_record_id": ["ATLAS_NUM"],
            "nris_refnum": ["REFNUM"],
            "date_listed": ["LISTED_DAT"],
        },
        "designation_types": ["National Register"],
        "designating_authority": "Texas Historical Commission",
        "active": True,
    },
    "TX_MARKERS": {
        "adapter": "gdb",
        "state_code": "TX",
        "name": "Texas Historical Markers (Atlas GDB)",
        "gdb_path": "manual-data/Texas/HistoricalMarkers.gdb",
        "layer": "HistoricalMarkers",
        "field_map": {
            "name": ["NAME"],
            "address": [],
            "city": [],
            "county": [],
            "state_record_id": ["MarkerNum"],
            "nris_refnum": [],
        },
        "designation_types": ["Historical Marker"],
        "designating_authority": "Texas Historical Commission",
        "active": True,
    },
    "TX_CEMETERIES": {
        "adapter": "gdb",
        "state_code": "TX",
        "name": "Texas Historic Cemeteries (Atlas GDB)",
        "gdb_path": "manual-data/Texas/Cemeteries.gdb",
        "layer": "CemeteriesPT",
        "field_map": {
            "name": ["CEMNAME"],
            "address": [],
            "city": [],
            "county": ["County"],
            "state_record_id": ["CEMNUM"],
            "nris_refnum": [],
        },
        "designation_types": ["Historic Cemetery"],
        "designating_authority": "Texas Historical Commission",
        "active": True,
    },
    "TX_COURTHOUSES": {
        "adapter": "gdb",
        "state_code": "TX",
        "name": "Texas County Courthouses (Atlas GDB)",
        "gdb_path": "manual-data/Texas/CountyCourthouses.gdb",
        "layer": "CountyCourthouses",
        "field_map": {
            "name": ["Courthouse_Name"],
            "address": [],
            "city": [],
            "county": [],
            "state_record_id": ["Atlas_Number"],
            "nris_refnum": [],
        },
        "designation_types": ["County Courthouse"],
        "designating_authority": "Texas Historical Commission",
        "active": True,
    },
    "TX_SITES": {
        "adapter": "gdb",
        "state_code": "TX",
        "name": "Texas State Historic Sites (Atlas GDB)",
        "gdb_path": "manual-data/Texas/StateHistoricSites.gdb",
        "layer": "StateHistoricSites",
        "field_map": {
            "name": ["P_NAME"],
            "address": [],
            "city": [],
            "county": ["COUNTY_1"],
            "state_record_id": ["CODE"],
            "nris_refnum": [],
        },
        "designation_types": ["State Historic Site"],
        "designating_authority": "Texas Historical Commission",
        "active": True,
    },
    "TX_MUSEUMS": {
        "adapter": "gdb",
        "state_code": "TX",
        "name": "Texas Museums (Atlas GDB)",
        "gdb_path": "manual-data/Texas/Museums.gdb",
        "layer": "Museums",
        "field_map": {
            "name": ["MUSNAME"],
            "address": ["STRADDRSS"],
            "city": ["CITY"],
            "county": ["COUNTY"],
            "state_record_id": ["ATLAS_NUM"],
            "nris_refnum": [],
        },
        "designation_types": ["Museum"],
        "designating_authority": "Texas Historical Commission",
        "active": True,
    },
    "NJ": {
        "adapter": "arcgis",
        "name": "New Jersey Historic Properties",
        "endpoint": (
            "https://mapsdep.nj.gov/arcgis/rest/services/"
            "Features/Land/MapServer/55/query"
        ),
        "field_map": {
            "name": ["NAME"],
            "address": ["ADDRESS"],
            "city": [],
            "county": [],
            "state_record_id": ["NJEMS_PIID"],
            "date_constructed": [],
            "nris_refnum": ["NRIS_ID"],
            "date_listed": ["NRDATE"],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register", "National Register"],
        "designating_authority": "New Jersey HPO",
        "active": True,
    },
    "MD": {
        "adapter": "arcgis",
        "name": "Maryland Inventory of Historic Properties",
        "endpoint": (
            "https://mdpgis.mdp.state.md.us/arcgis/rest/services/"
            "MHT/Medusa/FeatureServer/3/query"
        ),
        "field_map": {
            "name": ["NAMEHIST", "NAMEOTHER"],
            "address": ["FULLADDR"],
            "city": ["TOWN"],
            "county": ["COUNTYNAME"],
            "state_record_id": ["MIHPNO"],
            "date_constructed": [],
            "nris_refnum": [],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register"],
        "designating_authority": "Maryland Historical Trust",
        "active": True,
    },
    "MD_NR": {
        "adapter": "arcgis",
        "state_code": "MD",
        "name": "Maryland National Register of Historic Places",
        "endpoint": (
            "https://mdpgis.mdp.state.md.us/arcgis/rest/services/"
            "MHT/Medusa/FeatureServer/1/query"
        ),
        "field_map": {
            "name": ["NRNAME", "ALTNAME"],
            "address": [],
            "city": [],
            "county": [],
            "state_record_id": ["NATREGID"],
            "date_constructed": [],
            "nris_refnum": ["NRREFNO"],
            "date_listed": ["LISTEDDATE"],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["National Register"],
        "designating_authority": "Maryland Historical Trust",
        "active": True,
    },
    "WA": {
        "adapter": "arcgis",
        "name": "Washington DAHP Register Properties",
        "endpoint": (
            "https://services6.arcgis.com/yIPFYZqx6a8IC4Hk/arcgis/rest/services/"
            "DAHP_%E2%80%93_Register_Properties/FeatureServer/0/query"
        ),
        "field_map": {
            "name": ["Comments"],
            "address": ["STREET_ADD"],
            "city": [],
            "county": [],
            "state_record_id": ["SITE_ID"],
            "date_constructed": [],
            "nris_refnum": [],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register", "National Register"],
        "designating_authority": "Washington DAHP",
        "active": True,
    },
    "HI": {
        "adapter": "arcgis",
        "name": "Hawaii NRHP Points",
        "endpoint": (
            "https://services3.arcgis.com/fsrDo0QMPlK9CkZD/arcgis/rest/services/"
            "Hawaii_NRHP_Points/FeatureServer/0/query"
        ),
        "field_map": {
            "name": ["RESNAME"],
            "address": [],
            "city": [],
            "county": [],
            "state_record_id": ["CR_ID"],
            "date_constructed": [],
            "nris_refnum": ["NRIS_Refnum"],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["National Register"],
        "designating_authority": "Hawaii SHPO",
        "active": True,
    },
    # --- Maine ---
    "ME": {
        "adapter": "arcgis",
        "state_code": "ME",
        "name": "Maine CARMA Historic Properties",
        "endpoint": (
            "https://arcgisserver.maine.gov/arcgis/rest/services/"
            "mdot/MaineDOT_Feature/MapServer/45/query"
        ),
        "field_map": {
            "name": ["HISTPROP.HIST_PROP_FORM_V.PROPNAM_HIS", "HISTPROP.HIST_PROP_FORM_V.PROPNAME_OTH"],
            "address": ["HISTPROP.HIST_PROP_FORM_V.ST_E911_PROP"],
            "city": ["HISTPROP.HIST_PROP_FORM_V.TOWN"],
            "county": ["HISTPROP.HIST_PROP_FORM_V.COUNTY"],
            "state_record_id": ["HISTPROP.HIST_PROP_FORM_V.MHPC_INV_NUM"],
            "date_constructed": ["HISTPROP.HIST_PROP_FORM_V.DATE_ESTCON"],
            "nris_refnum": [],
            "date_listed": [],
        },
        "pagination": "objectid",
        "page_size": 100,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.3,
        "designation_types": ["State Register"],
        "designating_authority": "Maine Historic Preservation Commission",
        "active": True,
    },
    # --- Washington DC ---
    "DC": {
        "adapter": "arcgis",
        "state_code": "DC",
        "name": "DC Historic Landmarks",
        "endpoint": (
            "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/"
            "Planning_Landuse_and_Zoning_WebMercator/MapServer/22/query"
        ),
        "field_map": {
            "name": ["NAME"],
            "address": [],
            "city": [],
            "county": [],
            "state_record_id": ["UNIQUEID"],
            "date_constructed": [],
            "nris_refnum": [],
            "date_listed": ["DESIGNATIONDATE"],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["DC Landmark", "National Register"],
        "designating_authority": "DC Historic Preservation Office",
        "active": True,
    },
    # --- Delaware ---
    "DE": {
        "adapter": "arcgis",
        "state_code": "DE",
        "name": "Delaware Historic Markers",
        "endpoint": (
            "https://enterprise.firstmap.delaware.gov/arcgis/rest/services/"
            "Society/DE_HistoricMarkers/FeatureServer/0/query"
        ),
        "field_map": {
            "name": ["MARKER_NAME"],
            "address": ["STREET_ADDRESS"],
            "city": ["CITY"],
            "county": [],
            "state_record_id": ["MARKER_NUMBER"],
            "date_constructed": [],
            "nris_refnum": [],
            "date_listed": [],
        },
        "page_size": 2000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Historical Marker"],
        "designating_authority": "Delaware SHPO",
        "active": True,
    },
    # --- Kansas ---
    "KS": {
        "adapter": "arcgis",
        "state_code": "KS",
        "name": "Kansas KHRI Historic Resources Inventory",
        "endpoint": (
            "https://services.kgs.ku.edu/arcgis8/rest/services/"
            "khri/khri/MapServer/4/query"
        ),
        "field_map": {
            "name": ["HISTNAME"],
            "address": ["SITUS_NUM", "SITUS_PR00", "SITUS_ST01", "SITUS_ST02"],
            "city": ["SITUS_CI01"],
            "county": [],
            "state_record_id": ["INVENTOR00"],
            "date_constructed": [],
            "nris_refnum": [],
            "date_listed": [],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register"],
        "designating_authority": "Kansas Historical Society",
        "active": True,
    },
    # --- Michigan (markers only) ---
    "MI": {
        "adapter": "arcgis",
        "state_code": "MI",
        "name": "Michigan Historical Markers",
        "endpoint": (
            "https://services3.arcgis.com/Jdnp1TjADvSDxMAX/ArcGIS/rest/services/"
            "Historical_Markers_Public_View/FeatureServer/0/query"
        ),
        "field_map": {
            "name": ["markername"],
            "address": ["markerlocationaddress"],
            "city": ["markerlocationcity"],
            "county": [],
            "state_record_id": [],
            "date_constructed": [],
            "nris_refnum": [],
            "date_listed": [],
        },
        "page_size": 2000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Historical Marker"],
        "designating_authority": "Michigan SHPO",
        "active": True,
    },
    # --- Oklahoma ---
    "OK": {
        "adapter": "arcgis",
        "state_code": "OK",
        "name": "Oklahoma SHPO National Register Listed Sites",
        "endpoint": (
            "https://services.arcgis.com/nmcSvtJjWBnsYp7Y/arcgis/rest/services/"
            "NR_LISTEDSITES/FeatureServer/0/query"
        ),
        "field_map": {
            "name": ["Property_N"],
            "address": [],
            "city": ["City"],
            "county": ["County"],
            "state_record_id": [],
            "date_constructed": [],
            "nris_refnum": [],
            "date_listed": [],
        },
        "page_size": 2000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["National Register"],
        "designating_authority": "Oklahoma SHPO",
        "active": True,
    },
    # --- Kentucky ---
    "KY": {
        "adapter": "arcgis",
        "state_code": "KY",
        "name": "Kentucky Heritage Council Historic Resources",
        "endpoint": (
            "https://services6.arcgis.com/enwYUUpKO0CdGERb/arcgis/rest/services/"
            "KHCPublicGIS_view/FeatureServer/2/query"
        ),
        "field_map": {
            "name": ["HName"],
            "address": ["LOCATION"],
            "city": ["TOWN"],
            "county": [],
            "state_record_id": ["SiteNo"],
            "date_constructed": ["ConstYear"],
            "nris_refnum": [],
            "date_listed": [],
        },
        "page_size": 2000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register"],
        "designating_authority": "Kentucky Heritage Council",
        "active": True,
    },
    # --- Louisiana ---
    "LA": {
        "adapter": "arcgis",
        "state_code": "LA",
        "name": "Louisiana NR Individual Listings",
        "endpoint": (
            "https://services6.arcgis.com/Pa9GX8gVoVoT9Dpj/arcgis/rest/services/"
            "NR_Individual_Listings/FeatureServer/1/query"
        ),
        "field_map": {
            "name": ["RESNAME"],
            "address": ["Address_1"],
            "city": ["City_1"],
            "county": ["Parish_1"],
            "state_record_id": [],
            "date_constructed": [],
            "nris_refnum": [],
            "date_listed": ["DateonRe_1"],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["National Register"],
        "designating_authority": "Louisiana SHPO",
        "active": True,
    },
    # --- Arkansas ---
    "AR": {
        "adapter": "arcgis",
        "state_code": "AR",
        "name": "Arkansas AHPP National Register and Survey Database",
        "endpoint": (
            "https://services2.arcgis.com/grRZsSQcS53444of/arcgis/rest/services/"
            "AHPP_National_Register_and_Survey_Database/FeatureServer/0/query"
        ),
        "field_map": {
            "name": ["Historic_N"],
            "address": ["House_Numb", "Dir", "Street_Nam", "Suffix"],
            "city": ["Town"],
            "county": ["County"],
            "state_record_id": ["Resource__"],
            "date_constructed": [],
            "nris_refnum": [],
            "date_listed": ["NR_List_Da"],
        },
        "page_size": 2000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register", "National Register"],
        "designating_authority": "Arkansas AHPP",
        "active": True,
    },
    # --- Illinois ---
    "IL": {
        "adapter": "arcgis",
        "state_code": "IL",
        "name": "Illinois IHPA HARGIS Properties",
        "endpoint": (
            "https://services.arcgis.com/b9DHj1BjfdLLFv11/arcgis/rest/services/"
            "IHPA_HARGIS/FeatureServer/0/query"
        ),
        "field_map": {
            "name": ["SignificantName"],
            "address": ["Location"],
            "city": ["City"],
            "county": ["County"],
            "state_record_id": ["RefNum"],
            "date_constructed": [],
            "nris_refnum": [],
            "date_listed": [],
        },
        "page_size": 2000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register"],
        "designating_authority": "Illinois IHPA",
        "active": True,
    },
    # --- Pennsylvania ---
    "PA": {
        "adapter": "arcgis",
        "state_code": "PA",
        "name": "Pennsylvania SHPO Above Ground Resources (PA-SHARE)",
        "endpoint": (
            "https://utility.arcgis.com/usrsvcs/servers/"
            "bb0205239d604bd88ff2d6620e8822fb/rest/services/"
            "PASHAREMAPGUEST/MapServer/2/query"
        ),
        "field_map": {
            "name": ["EntityName"],
            "address": ["ResourceAddress"],
            "city": [],
            "county": [],
            "state_record_id": ["EntityNum"],
            "date_constructed": [],
            "nris_refnum": [],
            "date_listed": [],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "Eligibility IN ('Listed','Eligible','NHL')",
        "rate_limit": 0.5,
        "designation_types": ["State Register", "National Register"],
        "designating_authority": "Pennsylvania SHPO",
        "active": True,
    },
    # --- Virginia ---
    "VA": {
        "adapter": "arcgis",
        "state_code": "VA",
        "name": "Virginia DHR Architecture Points (named properties only)",
        "endpoint": (
            "https://vcris.dhr.virginia.gov/arcgis/rest/services/"
            "dhr/dhr_public/MapServer/2/query"
        ),
        "field_map": {
            "name": ["PropertyNames"],
            "address": ["Addresses"],
            "city": [],
            "county": [],
            "state_record_id": ["DHR_ID"],
            "date_constructed": [],
            "nris_refnum": [],
            "date_listed": [],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": (
            "PropertyNames NOT LIKE 'House,%'"
            " AND PropertyNames NOT LIKE 'Single Dwelling,%'"
            " AND PropertyNames NOT LIKE 'Farm,%'"
            " AND PropertyNames NOT LIKE 'Barn,%'"
            " AND PropertyNames NOT LIKE 'Garage,%'"
            " AND PropertyNames NOT LIKE 'Store,%'"
            " AND PropertyNames NOT LIKE 'Church,%'"
            " AND PropertyNames NOT LIKE 'Cemetery,%'"
            " AND PropertyNames NOT LIKE 'Commercial building,%'"
            " AND PropertyNames NOT LIKE 'School,%'"
            " AND PropertyNames NOT LIKE 'Bridge,%'"
            " AND PropertyNames NOT LIKE 'Shed,%'"
            " AND PropertyNames NOT LIKE 'Office,%'"
            " AND PropertyNames NOT LIKE 'Warehouse,%'"
            " AND PropertyNames NOT LIKE 'Mill,%'"
        ),
        "rate_limit": 0.5,
        "designation_types": ["State Register"],
        "designating_authority": "Virginia DHR",
        "active": True,
    },
    "VA_NR": {
        "adapter": "arcgis",
        "state_code": "VA",
        "name": "Virginia VLR/NRHP/NHL Listed Properties",
        "endpoint": (
            "https://vcris.dhr.virginia.gov/arcgis/rest/services/"
            "dhr/dhr_public/MapServer/3/query"
        ),
        "field_map": {
            "name": ["PropertyNames"],
            "address": [],
            "city": [],
            "county": [],
            "state_record_id": ["DHR_ID"],
            "date_constructed": [],
            "nris_refnum": [],
            "date_listed": [],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["National Register", "Virginia Landmarks Register"],
        "designating_authority": "Virginia DHR",
        "active": True,
    },
    # --- New York ---
    "NY": {
        "adapter": "arcgis",
        "state_code": "NY",
        "name": "New York SHPO National Register Listings",
        "endpoint": (
            "https://services.arcgis.com/1xFZPtKn1wKC6POA/ArcGIS/rest/services/"
            "National_Register_Building_Listings/FeatureServer/13/query"
        ),
        "field_map": {
            "name": ["HistoricName"],
            "address": [],
            "city": ["CityTown"],
            "county": ["CountyName"],
            "state_record_id": ["NRNum"],
            "date_constructed": [],
            "nris_refnum": [],
            "date_listed": ["DateNR"],
        },
        "page_size": 2000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register", "National Register"],
        "designating_authority": "New York SHPO",
        "active": True,
    },
    # --- California ---
    "CA_LA": {
        "adapter": "arcgis",
        "state_code": "CA",
        "name": "LA Historic Resources (California State Historic Resources)",
        "endpoint": (
            "https://services5.arcgis.com/7nsPwEMP38bSkCjy/arcgis/rest/services/"
            "California_State_Historic_Resources/FeatureServer/4/query"
        ),
        "field_map": {
            "name": ["NAME"],
            "address": ["LOCATION"],
            "city": [],
            "county": [],
            "state_record_id": ["MNT_NUM"],
            "date_constructed": [],
            "nris_refnum": [],
            "date_listed": ["DATE_ACTIVE"],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["California Register", "State Register"],
        "designating_authority": "California OHP",
        "active": True,
    },
    "CA": {
        "adapter": "custom",
        "state_code": "CA",
        "name": "California OHP Listed Resources (statewide)",
        "designation_types": ["California Register", "State Register"],
        "designating_authority": "California Office of Historic Preservation",
        "active": True,
    },
    # --- National datasets ---
    "NRHP_NATIONAL": {
        "adapter": "arcgis",
        "state_code": "US",
        "name": "National Register of Historic Places - NPS Points",
        "endpoint": (
            "https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/"
            "nrhp_points_v1/FeatureServer/0/query"
        ),
        "field_map": {
            "name": ["RESNAME"],
            "address": ["Address"],
            "city": ["City"],
            "county": ["County"],
            "state_record_id": ["CR_ID"],
            "date_constructed": [],
            "nris_refnum": ["NRIS_Refnum"],
            "date_listed": ["CertDate"],
            "state_name_field": "State",
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "multi_state": True,
        "designation_types": ["National Register"],
        "designating_authority": "National Park Service",
        "active": True,
    },
    # --- Regional datasets ---
    "GA_ATL": {
        "adapter": "arcgis",
        "state_code": "GA",
        "name": "Georgia Historic Resources (Atlanta Region)",
        "endpoint": (
            "https://services1.arcgis.com/Ug5xGQbHsD8zuZzM/arcgis/rest/services/"
            "ARC_Historic_Resources/FeatureServer/0/query"
        ),
        "field_map": {
            "name": ["Name"],
            "address": ["ADDRESS"],
            "city": ["CITY"],
            "county": ["County"],
            "state_record_id": ["ResourceID"],
            "date_constructed": ["DateofConstruction"],
            "nris_refnum": [],
        },
        "page_size": 1000,
        "out_sr": 4326,
        "where": "1=1",
        "rate_limit": 0.5,
        "designation_types": ["State Register"],
        "designating_authority": "Georgia HPD",
        "active": True,
    },
}
