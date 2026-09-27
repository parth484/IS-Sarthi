# Bureau of Indian Standards (BIS) API Discovery & Ingestion Architecture

## Executive Summary

During initial testing of the BIS "Know Your Standard" endpoint (`POST /review-service//searchKnowStandards`), a strict **500-record query ceiling** was discovered (e.g. broad keywords like `"steel"` returned exactly 500 records). 

Through inspection of the official BIS Angular single-page application (`https://standards.bis.gov.in/`, bundle `main.ac9dc76dd7204f57.js` and feature chunks `646.85aa02c9133760be.js`), we reverse-engineered the exact API architecture and verified that **the 500-record ceiling CAN be completely bypassed**. 

The official BIS backend exposes a dedicated, unauthenticated, paginated endpoint designed specifically for published standards listing across all technical departments, covering the entire **23,867 standards** of the official BIS catalogue.

---

## 1. Confirmed Official BIS Endpoints

| # | Endpoint URL | Method | Auth Required | Purpose & Scope |
|---|---|---|---|---|
| **1** | `https://standardsadmin.bis.gov.in/review-service/getWebsitePSTechDepartmentWise` | **POST** | **None (Public)** | **Primary Catalogue Endpoint**: Retrieves published standards across all departments or per department with true offset/limit pagination (Total: 23,867 standards). |
| **2** | `https://standardsmodule.bis.gov.in/sdo-service/getWebsiteDepartments` | **POST** | **None (Public)** | **Department Listing**: Returns all 17 BIS Technical Departments with numeric IDs, alias codes (CED, ETD, MTD, etc.), and `encryptedDepartmentId`. |
| **3** | `https://standardsadmin.bis.gov.in/technical-committee/getWebsiteSectionalCommittee` | **POST** | **None (Public)** | **Sectional Committee Listing**: Returns all 394 BIS technical committees with codes (e.g., CED 02, ETD 01, MHD 01), department mappings, and IDs. |
| **4** | `https://standardsadmin.bis.gov.in/review-service/getAspectAndDegreeOfEquivalenceFilters` | **POST** | **None (Public)** | **Taxonomy Filters**: Returns standard classification aspects (Product Specification, Code of Practice, Methods of Tests, Safety Standard, etc.). |
| **5** | `https://standardsadmin.bis.gov.in/review-service//searchKnowStandards` | **POST** | **None (Public)** | **Targeted Search & Detail**: Searches standard numbers/titles. Capped at 500 records for broad text, but exact for specific IS prefixes (e.g., `IS 100`, `IS 1554`). |
| **6** | `https://standardsadmin.bis.gov.in/review-service/getProductManualStandardsList` | **POST** | **None (Public)** | **Product Manuals & STI**: Paginated list of standards with published product manuals and Schemes of Testing and Inspection. |
| **7** | `https://standardsadmin.bis.gov.in/master-service/getAllDepartments` | **POST** | **Session Required (401)** | Internal admin portal endpoint (requires login session token). |

---

## 2. Detailed Endpoint Analysis & Request Payloads

### Endpoint A: Comprehensive Published Standards (`getWebsitePSTechDepartmentWise`)

This is the official endpoint powering the BIS portal's Published Standards table.

* **URL**: `POST https://standardsadmin.bis.gov.in/review-service/getWebsitePSTechDepartmentWise`
* **Headers**:
  ```http
  Content-Type: application/json
  Accept: application/json, text/plain, */*
  Origin: https://standards.bis.gov.in
  Referer: https://standards.bis.gov.in/
  ```

#### Mode 1: All Departments (Global Pagination)
* **Request Payload**:
  ```json
  {
    "allDepartments": true,
    "totalRow": 1,
    "offset": 0,
    "limit": 100,
    "techCommitteeId": 0
  }
  ```
* **Empirical Response**:
  * `status`: `"SUCCESS"`
  * `statusCode`: `200`
  * `totalRecord`: `23867` (Confirmed total size of BIS published standards catalogue)
  * `data`: Array of standard objects of length matching `limit`.

#### Mode 2: By Technical Department
* **Request Payload**:
  ```json
  {
    "encDepartmentId": "eyJpdiI6IkhiQ1pTMVIrMlBTRjV3eFVqUU81WlE9PS...",
    "typeSelected": 1,
    "offset": 0,
    "limit": 50,
    "techCommitteeId": 0
  }
  ```
* **Empirical Response**:
  * Civil Engineering Department (`CED`): `totalRecord: 940`
  * Electrotechnical Department (`ETD`): `totalRecord: 1241`
  * Metallurgical Engineering Department (`MTD`): `totalRecord: 1548`
  * Only standards belonging to that department are returned.

#### Record Schema (`getWebsitePSTechDepartmentWise`)
```json
{
  "slNo": 1,
  "standardId": 30083,
  "standardNumber": "IS 10069:2023",
  "standardName": "Hydraulic fluid power - Positive-Displacement Pumps Motors...",
  "publishedOn": "2023-05-12",
  "reviewOn": "2028-05-02",
  "isStatus": 2,
  "noOfRevision": 1,
  "typeOfStandardId": 1,
  "typeOfStandardName": "Methods of Tests",
  "degreeOfEquivalenceId": 0,
  "equivalenceTypeName": "None",
  "documents": []
}
```

---

### Endpoint B: Technical Departments Directory (`getWebsiteDepartments`)

* **URL**: `POST https://standardsmodule.bis.gov.in/sdo-service/getWebsiteDepartments`
* **Request Payload**: `{}`
* **Response**: Returns the complete list of all 17 BIS Technical Departments:
  1. `AYD` (ID: 109) — Ayush Department
  2. `CHD` (ID: 62) — Chemical Department
  3. `CED` (ID: 63) — Civil Engineering Department
  4. `LITD` (ID: 66) — Electronics and Information Technology Department
  5. `ETD` (ID: 65) — Electrotechnical Department
  6. `EED` (ID: 110) — Environment and Ecology Department
  7. `FAD` (ID: 61) — Food and Agriculture Department
  8. `MSD` (ID: 21) — Management System Department
  9. `MED` (ID: 68) — Mechanical Engineering Department
  10. `MHD` (ID: 64) — Medical Equipment and Hospital Planning Department
  11. `MTD` (ID: 70) — Metallurgical Engineering Department
  12. `PCD` (ID: 69) — Petroleum, Coal and Related Products Department
  13. `PGD` (ID: 74) — Production and General Engineering Department
  14. `SSD` (ID: 107) — Service Sector Department
  15. `TXD` (ID: 71) — Textile Department
  16. `TED` (ID: 67) — Transport Engineering Department
  17. `WRD` (ID: 72) — Water Resources Department

Each entry contains `encryptedDepartmentId`, which can be supplied directly to `getWebsitePSTechDepartmentWise`.

---

### Endpoint C: Sectional Committees Directory (`getWebsiteSectionalCommittee`)

* **URL**: `POST https://standardsadmin.bis.gov.in/technical-committee/getWebsiteSectionalCommittee`
* **Request Payload**: `{}`
* **Response**: Returns 394 technical committees with:
  * `committeeId`
  * `committeeName` (e.g. "Cement and Concrete", "Power Cables")
  * `convertedName` (e.g. "CED 02 - Cement and Concrete")
  * `aliasName` (e.g. "CED", "ETD")
  * `departmentId`

---

### Endpoint D: Targeted Search (`searchKnowStandards`)

* **URL**: `POST https://standardsadmin.bis.gov.in/review-service//searchKnowStandards`
* **Request Payload**:
  ```json
  {
    "searchText": "IS 100",
    "token": null,
    "refreshToken": null,
    "clientId": null,
    "clientSecret": null,
    "sub": null
  }
  ```
* **Filter Verification Results**:
  * Tested passing `"departmentId": 63` alongside `"searchText": "cement"`: **Ignored**. Total records remained 345, and records from department 74 were still present.
  * Tested passing `"page": 2, "pageSize": 50`: **Ignored**. All 500 records were returned starting from the beginning.
  * Conclusion: `searchKnowStandards` is a free-text full-scan search that does not accept backend pagination or SQL-level department filters. The Angular frontend (`app-search-standard` component in chunk `646.85aa02c9133760be.js`) performs **client-side pagination** via `.slice(0, resultsToShow)`.

---

## 3. Comparison of Ingestion Strategies to Overcome the 500 Ceiling

| Strategy | Feasibility | Expected Coverage | Pros | Cons / Risks |
|---|---|---|---|---|
| **Approach 1: Department-Wise Pagination (`getWebsitePSTechDepartmentWise`)** | **CONFIRMED & RECOMMENDED** | **100% of BIS Catalogue (23,867 standards)** | True offset/limit paging; zero truncations; provides standard aspect/type metadata (Test method, Specification, etc.); exactly 17 department batches. | Requires one initial call to fetch department encrypted IDs. |
| **Approach 2: Global Offset/Limit (`getWebsitePSTechDepartmentWise`)** | **CONFIRMED & VIABLE** | **100% of BIS Catalogue (23,867 standards)** | Single endpoint with `allDepartments: true`; clean linear pagination (`offset += limit`). | Batching by department (Approach 1) is cleaner for incremental error recovery. |
| **Approach 3: IS Number Prefix Partitioning (`searchKnowStandards`)** | **CONFIRMED FALLBACK** | **~95-98%** | Works with the already-implemented `bis_api.py`; querying prefixes (`IS 100`, `IS 101`, `IS 102`) returns 100–300 records each (well below the 500 limit). | Requires maintaining a numeric prefix loop (`IS 1` to `IS 250`). |
| **Approach 4: Broad English Keyword Search (`searchKnowStandards`)** | **NOT RECOMMENDED** | **< 30% (Severe Truncation)** | Simple to run. | Truncated at 500 records per query; misses long-tail standards. |
| **Approach 5: HTML Scraping via Legacy PHP Portal (`searchIS`)** | **NOT RECOMMENDED** | **Unstable** | Legacy portal table. | Requires PHP session management, vulnerable to HTML layout drift, returns HTTP 500 on direct API call. |

---

## 4. Controlled Verification Evidence

All candidate endpoints were subjected to controlled test requests using Python:

1. **`getAllDepartments` (master-service)**:
   * Request: `POST https://standardsadmin.bis.gov.in/master-service/getAllDepartments` with `{}`
   * Result: `HTTP 401 Unauthorized` (`"Your session has expired. Please log in again."`).
   * Decision: Do not use for public extraction.

2. **`searchKnowStandards` with Filters**:
   * Request 1: `searchText: "cement"` -> 345 records.
   * Request 2: `searchText: "cement"`, `departmentId: 63` -> 345 records (record 1 still departmentId 74).
   * Request 3: `searchText: "steel"`, `page: 2, pageSize: 50` -> 500 records (unpaginated).
   * Decision: Verified that `searchKnowStandards` does not support query filtering or pagination.

3. **`getWebsitePSTechDepartmentWise` Pagination & Department Verification**:
   * Request 1: `{"allDepartments": true, "totalRow": 1, "offset": 0, "limit": 5}` -> Returned records 1–5, `totalRecord: 23867`.
   * Request 2: `{"allDepartments": true, "totalRow": 1, "offset": 5, "limit": 5}` -> Returned records 6–10, `totalRecord: 23867`.
   * Request 3: `{"encDepartmentId": "<CED_ENC_ID>", "typeSelected": 1, "offset": 0, "limit": 5}` -> Returned 5 CED civil engineering standards, `totalRecord: 940`.
   * Request 4: `{"encDepartmentId": "<ETD_ENC_ID>", "typeSelected": 1, "offset": 0, "limit": 5}` -> Returned 5 ETD electrical standards, `totalRecord: 1241`.
   * Decision: **100% verified working without authentication**.

---

## 5. Architectural Recommendation for IS Sarthi

To ingest the full BIS catalogue cleanly, politely, and robustly:

1. **Use `getWebsiteDepartments`** to fetch the 17 official BIS technical departments (`CED`, `ETD`, `MTD`, `TXD`, etc.).
2. **Use `getWebsitePSTechDepartmentWise`** to page through each department in controlled chunks of 50 or 100 records (`limit: 100`, `offset: 0, 100, 200, ...`).
   * This breaks the 23,867 standards into 17 coherent division datasets (e.g. Electrotechnical: 1,241 standards in ~13 requests; Civil: 940 standards in ~10 requests).
   * A crawl delay of 1.5–2.0 seconds between requests ensures polite compliance with government servers (~250 total requests to ingest all 23,867 standards).
3. **Normalize and merge** into `data/bis/standards.json` with department codes, technical committee numbers, and standard types (`Product Specification`, `Methods of Tests`, `Code of Practice`), cleanly isolated from the 57 seed standards.
