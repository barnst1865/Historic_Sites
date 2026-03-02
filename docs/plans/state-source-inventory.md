# State Historic Preservation Office (SHPO) — Data Source Inventory

**Compiled:** 2026-03-02
**Purpose:** Catalog every state and territory's SHPO data availability to guide adapter development.

---

## Summary

| Adapter Type | Count | States |
|---|---|---|
| `arcgis` | 28 | AL, AR, CT, DC, DE, FL, ID, IL, IN, KY, MD, MA, ME, MO, MT, NC, NJ, OK, OR, PA, RI, TN, TX, UT, VA, VT, WV, WY* |
| `csv` | 1 | CA |
| `html_scraper` | 6 | IA, KS, LA, MS, OH, SC |
| `custom` | 8 | CO, GA, HI, MN, NE, NV, NY, SD, WA |
| `manual` | 13 | AK, AZ, GU, AS, MI, MP, ND, NH, NM, PR, VI, WI, WY |

*Note: Some states classified as `arcgis` need endpoint URL discovery from web apps (CT, IL, NE, OK). Some `custom` states may become `arcgis` once endpoints are confirmed (MN, NE, SD).*

**Estimated total records across all open sources: ~2.5M+**

---

## Tier 1: ArcGIS REST — Open Access (build first)

These states have confirmed or likely ArcGIS REST endpoints with no authentication required.

| State | Endpoint/Download URL | Est. Records | Designation Types | Notes |
|---|---|---|---|---|
| **IN** | `https://gisdata.in.gov/server/rest/services/Hosted/IDNR_Historic_Structures/FeatureServer` | **205,965** | NR, state surveyed (rated by significance) | Verified. Single layer, MaxRecordCount=1000. Best Midwest source. |
| **FL** | ArcGIS Hub: `STAUG::florida-master-site-file-historical-standing-structures-` | **181,000** structures | NR, surveyed structures, cemeteries, districts, bridges | Archaeological sites restricted by FL law. Structures layer open. |
| **TN** | `https://tnmap.tn.gov/arcgis/rest/services/HISTORICAL/HISTORICAL_COMMISSION/MapServer` | **168,371** | NR, surveyed resources | Also on ArcGIS Hub. Paper-to-digital conversion ongoing. |
| **UT** | `https://shpo.utah.gov/server/rest/services/Hosted/Historic_Utah_Buildings/FeatureServer/0` | **136,894** | NR, UT State Register, local designations | Verified. Rich fields incl. NRIS number, style, use, NR status. MaxRecordCount=2000. |
| **NC** | `https://gis2.ncdcr.gov/dncrgis/rest/services/NCHPO_Public/NCHPO_Historic_Resources_CNC/MapServer` | **130,000+** | NR, Study List, DOE, local landmarks/districts | Also offers full shapefile downloads. SRID 2264. Updated daily. |
| **MD** | `https://geodata.md.gov/imap/rest/services/Historic/` (verify migration to mdgeodata.md.gov) | **90,000** (MIHP) | MD Inventory, NR, DOE, Easements, Heritage Areas | Excellent. Also has Medusa HTML search. URL may have migrated. |
| **OR** | `https://maps.prd.state.or.us/arcgis/rest/services/Cultural/HistoricSites/MapServer/0` | **~67,000** | NR, state inventory, districts | Verified. Rich fields: name, address, yrBuilt, style, NR status. MaxRecordCount=1000. |
| **MA** | `http://arcgisserver.digital.mass.gov/arcgisserver/rest/services/AGOL/MHC_Inventory/FeatureServer` | **233,000** | NR, local districts, preservation restrictions, state inventory | Best-in-class. Also has downloadable SHP/GDB via MassGIS. |
| **VA** | `https://vcris.dhr.virginia.gov/arcgis/rest/services/dhr/dhr_public/MapServer` | **200,000+** (public layers limited) | VLR, NR, NHLs, districts, easements | Public MapServer has limited layers. Full V-CRIS is paid. MaxRecordCount=1000. |
| **TX** | `https://mappingtexashistory.thc.texas.gov/arcgis/rest/services/Historical/MapServer` + SHP/GDB download at `atlas.thc.texas.gov/Data/GISData` | **300,000+** | NR, SAL, RTHL, HTC, markers | Both ArcGIS REST and full shapefile/GDB download. Also per-county raw data. |
| **DC** | `https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Historic/MapServer` + Open Data: `opendata.dc.gov` | **27,000+** protected; 193K in HistoryQuest | DC Inventory, NR, NHLs, districts | Open Data DC has CSV/SHP/GeoJSON/KML download. HistoryQuest has 193K buildings. |
| **AL** | ArcGIS Hub: `ahcopendataportal-alabama.hub.arcgis.com` | **~2,900** (NR + AL Register) | NR, AL Register of Landmarks & Heritage, DOE, markers, cemeteries | Multiple layers with download in CSV/GeoJSON/SHP/KML. |
| **AR** | `https://gis.arkansas.gov/arcgis/rest/services/FEATURESERVICES/Society/FeatureServer` | **~2,700+** NR | NR, districts | State GIS hosts NR points + district polygons. Clean fields. |
| **WV** | `https://services.wvgis.wvu.edu/arcgis/rest/services/Society/wv_SHPO_public/FeatureServer` | Thousands | NR, architectural survey, cemeteries | Both MapServer and FeatureServer. 6 layers. MaxRecordCount=2000. |
| **KY** | `https://kygisserver.ky.gov/arcgis/rest/services/WGS84WM_Services/Ky_National_Register_Landmarks_WGS84WM/MapServer` | **~3,400** NR (~42K features) | NR, NHLs, surveyed resources | MaxRecordCount=1000. SRID 3857. 4th most NR listings nationally. |
| **NJ** | NJDEP Open Data: `gisdata-njdep.opendata.arcgis.com/datasets/njdep::historic-properties-of-new-jersey` | Unknown | NR, State Register, districts, local landmarks | Download as SHP/CSV/GeoJSON/KML. Must credit NJDEP GIS. |
| **RI** | RIGIS: `rigis-edc.opendata.arcgis.com/datasets/edc::historic-sites` | **17,500+** NR | NR, State Register, local districts | ArcGIS Hub with download. Points + district polygons. |
| **VT** | `https://anrmaps.vermont.gov/arcgis/rest/services/map_services/ACCD_Historic_NAPC/FeatureServer` | **30,000+** | VT State Register, NR, NHLs, districts | Both MapServer and FeatureServer. Also on VT Open Geodata Portal. |
| **MO** | `https://gis.dnr.mo.gov/server/rest/services/cultural/historic_districts_and_sites/MapServer` | **~6,946** | NR sites/districts, certified local districts, architectural surveys | Verified. 4 layers. Rich schema (Criteria A-D, Areas of Significance). EPSG:26915 needs reprojection. MaxRecordCount=2000. |
| **ME** | `https://arcgisserver.maine.gov/arcgis/rest/services/mdot/MaineDOT_Feature/MapServer/45` | **16,000+** survey records | NR, State Register, NR-eligible | Via MaineDOT CARMA. Incomplete — not all NR sites included. |
| **ID** | `https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/jG8BM/FeatureServer/0` | **7,415** | NR | Verified. NRHP layer only. Full inventory (103K) in restricted ICRIS. |
| **MT** | `https://services.arcgis.com/qnjIrwR8z5Izc0ij/arcgis/rest/services/National_Register_Historic_Properties/FeatureServer/4` | **988** | NR, districts, NHLs | Verified. Small but clean. Separate layers for districts/NHLs. MaxRecordCount=2000. |
| **PA** | PA-SHARE: `share.phmc.pa.gov/pashare/landing` + GIS Hub: `gis-hub-pennshare.hub.arcgis.com` | **136,000+** | NR, state-eligible, districts, markers | Built on ArcGIS Enterprise. Guest access for search; export may need Pro tier. |
| **DE** | CHRIS: `chris-users.delaware.gov/public/` + FirstMap: `opendata.firstmap.delaware.gov` | **~700+** NR | NR, State Register | Public map available; bulk data may need CHRIS account. |
| **CT** | ConnCRIS: `conncris.ct.gov` + GIS: `geodata.ct.gov` | **~75,000** | State Register, NR, local districts | ArcGIS Online. Need to extract underlying FeatureServer URL. |
| **IL** | HARGIS: `dnrhistoric.illinois.gov/preserve/hargis.html` | Unknown (large) | NR, NR-eligible, surveyed | ArcGIS-based since 2021. Legacy endpoint may be dead — need to discover current URL. |
| **OK** | ArcGIS Online item: `arcgis.com/home/item.html?id=abda0e849b874bb29587f7c22f653517` | **~1,400** NR | NR, Section 106 eligible, OK Landmarks Inventory | Need to extract FeatureServer URL from web map. |

---

## Tier 2: CSV Download (build second)

| State | Download URL | Est. Records | Designation Types | Notes |
|---|---|---|---|---|
| **CA** | BERD: `ohp.parks.ca.gov/?page_id=30338` | **~300,000+** (58 county files) | CA Register, CA Historical Landmarks, Points of Historical Interest, NR | Per-county CSV files. No spatial data — address-based, will need geocoding. CHRIS GIS is $150/hr. |

---

## Tier 3: HTML Scraper (build third)

| State | Search URL | Est. Records | Designation Types | Notes |
|---|---|---|---|---|
| **IA** | `shporecords.opportunityiowa.gov` | **~15,000+** | NR, state inventory | Wildcard search (*). No API or download. |
| **KS** | KHRI: `khri.kansasgis.org` | Unknown | NR, surveyed properties | ColdFusion app. Has "Download to Excel" button — may simplify scraping. |
| **LA** | `crt.state.la.us/.../national-register/database/index` | **~1,300** NR | NR, districts, surveyed structures | GIS map is login-gated ($1,300/yr). NR database is free HTML. |
| **MS** | `apps.mdah.ms.gov/Public/search.aspx` | **~40,000+** files | NR, MS Landmarks, districts, surveyed | HSMT full access is $1,300/yr. Public search is free HTML. |
| **OH** | `nr.ohpo.org` | **~4,000+** NR | NR, OH inventories | Free NR search. Full OMS GIS is $200/yr. |
| **SC** | SCHPR: `schpr.sc.gov` | **~82,000** survey; ~1,400 NR | NR, surveyed, districts | ArchSite GIS has no public API. SCHPR is searchable HTML. |

---

## Tier 4: Custom Adapter (build fourth)

| State | System | Est. Records | Designation Types | Notes |
|---|---|---|---|---|
| **GA** | GNAHRGIS: `gnahrgis.org` | **127,384** | NR, GA Register, surveyed | Free registration required. CSV/Excel export available. Java web app. |
| **MN** | MnSHIP: `mnship.gisdata.mn.gov` | **100,000+** | NR, state inventory | ArcGIS feature layers behind login. CSV export for credentialed users. Endpoint discovery needed. |
| **NY** | CRIS: `cris.parks.ny.gov` | **120,000+** | NR, State Register, NYC LPC, CLG, districts | ArcGIS Server with NY.gov auth. Guest mode limited. High value. |
| **CO** | Compass: `gis.colorado.gov/compass_oahp/` | **180,000+** | CO State Register, NR, districts | Requires approved application (free). Angular web app. |
| **WA** | WISAARD: `wisaard.dahp.wa.gov` | **~10,300** registered | WA Heritage Register, Heritage Barns, NR, districts | ArcGIS endpoint rejects external connections. Session-based web app. |
| **NE** | `gis.ne.gov/portal/apps/webappviewer/...` | **~1,100** NR | NR, NE State Register | Web app viewer; need to inspect for REST endpoint. |
| **SD** | CRGRID: `apps.sd.gov/DE71SHPOCRGRID/` | Unknown | NR, state survey | Public query UI. ArcGIS Online behind the scenes. |
| **NV** | ArcGIS web app (firewalled REST) | **~400** NR | NV State Register, NR | Interactive map public but REST endpoint blocked. PDF listing available. |
| **HI** | Kipuka: `kipukadatabase.com/kipuka/` | **~1,054** state register | HI Register, NR, SIHP | OHA's ArcGIS Online app. No documented REST API. SHPD DB is internal-only. |

---

## Tier 5: Manual / Not Feasible (defer)

| State | Reason | NR Sites | Notes |
|---|---|---|---|
| **AK** | Restricted by state law (AS 40.25.110). Requires application + professional credentials. | ~400 | AHRS has 50K+ records but legally restricted. NR sites covered by federal data. |
| **AZ** | AZSITE requires vetting + fees. Hub pilot is Pima County only. | Unknown | No statewide public data. |
| **MI** | CRIS in beta, restricted to SOI-qualified professionals. Paid subscription expected 2026. | Unknown | Monitor for public release. |
| **ND** | No public online database. NDCRS is internal-only. | ~400 | NR sites covered by federal data. |
| **NH** | EMMIT+ requires free account (new Jan 2025). Custom web app, no REST API. | ~16,000 | Free but not automatable. Could request data extract. |
| **NM** | NMCRIS restricted to qualified professionals. Public portal "coming soon." | Unknown | Largest automated cultural resource DB in US, entirely behind auth. |
| **WI** | Paid annual subscription required (WHPD/WisAHRD). | ~138,000-153K | High-value but cost barrier. In-person access free by appointment. |
| **WY** | WyoTrack requires application + $30/section fees. | ~1,000+ markers | Cultural resource data restricted. |
| **PR** | No public database or GIS. PDF nominations only. | ~375 | NR sites covered by federal data. |
| **VI** | MapGeo (proprietary, not ArcGIS). Limited to district boundaries. | ~91 | Small enough for manual entry. |
| **GU** | No database. PDF/HTML listings only. | ~134 | NR sites covered by federal data. |
| **AS** | No online database. | ~31 | Fully covered by federal data. |
| **MP** | No online database. | ~37 | Fully covered by federal data. |

---

## Recommended Build Order (Top 15)

Based on record count, data quality, and implementation ease:

| # | State | Adapter | Records | Why |
|---|---|---|---|---|
| 1 | **TX** | `arcgis`/`csv` | 300K+ | ArcGIS + full SHP/GDB download. Massive and well-documented. |
| 2 | **MA** | `arcgis` | 233K | Open FeatureServer + downloadable SHP/GDB. Best-in-class. |
| 3 | **IN** | `arcgis` | 206K | Verified open FeatureServer. Highest confirmed count. |
| 4 | **VA** | `arcgis` | 200K+ | Public MapServer (limited layers). Full V-CRIS is paid. |
| 5 | **FL** | `arcgis` | 181K | ArcGIS Hub. Structures layer open. |
| 6 | **TN** | `arcgis` | 168K | State MapServer + ArcGIS Hub. |
| 7 | **UT** | `arcgis` | 137K | Verified. Rich metadata, MaxRecordCount=2000. |
| 8 | **PA** | `arcgis` | 136K | ArcGIS Enterprise. Guest access may limit export. |
| 9 | **NC** | `arcgis` | 130K | MapServer + shapefile downloads. Updated daily. |
| 10 | **MD** | `arcgis` | 90K | Open ArcGIS. Verify migrated URLs. |
| 11 | **CA** | `csv` | 300K+ | Per-county CSVs. No spatial data — needs geocoding. |
| 12 | **CT** | `arcgis` | 75K | ConnCRIS. Need to extract FeatureServer URL. |
| 13 | **OR** | `arcgis` | 67K | Verified open MapServer. Rich fields. |
| 14 | **DC** | `arcgis` | 27K+ | Open Data portal with every format. |
| 15 | **VT** | `arcgis` | 30K | Open FeatureServer on ANR Maps. |

These 15 states account for an estimated **2.3M+ records** and are all achievable with the `arcgis_adapter` (plus `csv_adapter` for CA).

---

## Coordinate Systems Noted

Most sources use EPSG:3857 (Web Mercator) or EPSG:4326 (WGS84). Exceptions requiring reprojection:
- **MO**: EPSG:26915 (UTM Zone 15N)
- **NC**: EPSG:2264 (NC State Plane)
- **MA**: NAD83 MA State Plane Meters
- **TN**: NAD83 TN State Plane (Feet)
- **WI** (if accessed): WTM83/NAD83
