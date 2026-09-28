# Claims Workspace Architecture and Flowcharts

This document contains the architecture diagrams for the Contoso Claims Processing Workspace. 

## 1. System Architecture

```mermaid
flowchart LR
    User[Claims handler or operations lead]
    Browser[React workspace\nVite dev server]
    API[FastAPI API\nport 8080]
    Pipeline[Claims pipeline]
    CU[Azure Content Understanding\nanalyzers]
    Vision[Azure OpenAI vision model]
    Agent[Claims review agent]
    KB[Existing policy Knowledge Base\nMCP retrieval]
    Table[Azure Table Storage\nclaim records and decisions]
    Files[Local claim evidence folders\nPDFs and images]
    Rules[Deterministic validation rules]
    Metrics[Operational metrics]

    User --> Browser
    Browser --> API
    API --> Files
    API --> Pipeline
    Pipeline --> CU
    Pipeline --> Vision
    Pipeline --> Rules
    Pipeline --> Agent
    Agent --> KB
    Pipeline --> Table
    API --> Table
    Table --> Metrics
    Metrics --> API
    API --> Browser
```

## 2. Original Claim-Preparation Flow

```mermaid
flowchart TD
    Start([Claim evidence available]) --> Ingest[Walk claim folder]
    Ingest --> Classify{Classify filename}
    Classify --> Documents[Document files]
    Classify --> Photos[Photographs]
    Documents --> Extract[Content Understanding analyzers]
    Extract --> Fields[Typed values + confidence + source]
    Photos --> Assess[Vision assessment]
    Assess --> PhotoFacts[Visible damage + repair band]
    Fields --> Validate[Deterministic validation]
    PhotoFacts --> Validate
    Validate --> Findings[Explainable findings]
    Fields --> Package[Claim package]
    PhotoFacts --> Package
    Findings --> Package
    Package --> Agent[Grounded claims agent]
    Agent --> KB[(Existing policy Knowledge Base)]
    KB --> Review[Structured summary + recommendation]
    Review --> Persist[Persist prepared claim]
    Findings --> Persist
    Persist --> Queue[Handler review queue]
```

## 3. Upload and Reprocessing Flow

```mermaid
sequenceDiagram
    actor User as User
    participant UI as React UploadClaim
    participant API as FastAPI
    participant FS as Claim evidence folder
    participant Job as Background pipeline
    participant Store as Azure Table Storage

    User->>UI: Enter claim ID and choose files
    UI->>API: POST /api/claims/submit multipart
    API->>API: Validate claim ID, file count, suffix, and size
    API->>FS: Save evidence files
    API-->>UI: processing status
    API->>Job: Schedule claim processing
    UI->>API: Poll /api/claims
    API-->>UI: processing contains claim ID
    Job->>Job: Extract, assess, validate, summarize
    Job->>Store: Save prepared result
    UI->>API: Poll /api/claims
    API-->>UI: Prepared result and processed timestamp
    UI-->>User: Processed and ready for handler review
```

## 4. Handler Decision Lifecycle

```mermaid
stateDiagram-v2
    [*] --> NotProcessed
    NotProcessed --> Processing: Process
    Processing --> Prepared: Pipeline succeeds
    Prepared --> AwaitingVerification: Critical low-confidence fields exist
    AwaitingVerification --> Prepared: Verification completed in decision form
    Prepared --> Accepted: Accept preparation
    Prepared --> RequestInformation: Request information
    Prepared --> Rejected: Reject preparation
    Prepared --> DuplicatePending: System finds possible duplicate
    DuplicatePending --> Accepted: Handler accepts preparation
    DuplicatePending --> RequestInformation: Handler requests information
    DuplicatePending --> Rejected: Handler rejects preparation
    DuplicatePending --> Duplicate: Handler confirms duplicate
    Accepted --> Accepted: Edit decision
    RequestInformation --> RequestInformation: Edit decision
    Rejected --> Rejected: Edit decision
    Duplicate --> Duplicate: Edit decision
    Accepted --> Archived: Archive
    RequestInformation --> Archived: Archive
    Rejected --> Archived: Archive
    Duplicate --> Archived: Archive
    Archived --> Accepted: Edit archived decision
    Archived --> RequestInformation: Edit archived decision
    Archived --> Rejected: Edit archived decision
    Archived --> Duplicate: Edit archived decision
```

## 5. Low-Confidence Verification Flow

```mermaid
flowchart TD
    Extracted[Extracted field with confidence] --> Critical{Field affects rules or outcome?}
    Critical -- No --> Display[Display confidence only]
    Critical -- Yes --> Threshold{Confidence below threshold?}
    Threshold -- No --> Ready[Ready for handler]
    Threshold -- Yes --> Item[Create verification item\nfield + value + source + confidence]
    Item --> Queue[Claim status: awaiting_verification]
    Queue --> Handler[Handler checks source document]
    Handler --> Confirm[Handler confirms item IDs]
    Confirm --> Decision[Decision API validates all confirmations]
    Decision --> Persist[Persist decision and confirmations]
```

## 6. Duplicate Detection and Human Review

```mermaid
flowchart TD
    Submit[New claim ID submitted] --> Process[Run normal extraction]
    Process --> Identity[Normalize policy number, VIN, date of loss]
    Identity --> Complete{All strong identity fields available?}
    Complete -- No --> Normal[Normal handler queue]
    Complete -- Yes --> Lookup[Compare against persisted claims]
    Lookup --> Match{Different claim with same identity?}
    Match -- No --> Normal
    Match -- Yes --> Pending[Status: duplicate_pending]
    Pending --> Show[Show matching claim ID and evidence]
    Show --> Handler{Human handler decision}
    Handler --> Confirm[Mark as duplicate]
    Handler --> Accept[Accept preparation]
    Handler --> Info[Request information]
    Handler --> Reject[Reject preparation]
    Confirm --> FinalDuplicate[Status: duplicate]
    Accept --> Accepted[Status: accepted]
    Info --> Request[Status: request_information]
    Reject --> Rejected[Status: rejected]
```

## 7. Metrics Flow

```mermaid
flowchart LR
    Claims["Azure Table claim records"] --> Aggregate["store.metrics()"]
    Aggregate --> Recommendations["Recommendation mix"]
    Aggregate --> Findings["Finding-code prevalence"]
    Aggregate --> Missing["Missing-document counts"]
    Aggregate --> Estimates["Estimate distribution"]
    Aggregate --> Time["Average preparation time"]
    Aggregate --> Operations["Waiting on policyholder<br/>Senior-adjuster referrals<br/>Cleared without finding"]
    Recommendations --> API["GET /api/metrics"]
    Findings --> API
    Missing --> API
    Estimates --> API
    Time --> API
    Operations --> API
    API --> Dashboard["MetricsOverview"]
    Dashboard --> Drilldown["Claim IDs behind each metric"]
```

## 8. File-to-Flow Mapping

```mermaid
flowchart TD
    Config[backend/config.py] --> Services[Service endpoints, table names, limits]
    Analyzers[backend/analyzers.py] --> Extract[Document extraction]
    CU[backend/content_understanding.py] --> Extract
    Vision[backend/vision.py] --> Photos[Photo assessment]
    Validation[backend/validation.py] --> Rules[Deterministic findings]
    Verification[backend/verification.py] --> Human[Verification workflow]
    Agent[backend/claims_agent.py] --> Grounding[Grounded review]
    Pipeline[backend/pipeline.py] --> Orchestration[End-to-end orchestration]
    Store[backend/store.py] --> Persistence[Claims, decisions, metrics]
    API[backend/api.py] --> Endpoints[HTTP endpoints]
    Upload[frontend/src/components/UploadClaim.jsx] --> API
    List[frontend/src/components/ClaimList.jsx] --> Queue[Lifecycle sections]
    Detail[frontend/src/components/ClaimDetail.jsx] --> Evidence[Claim evidence and findings]
    Decision[frontend/src/components/DecisionPanel.jsx] --> Human
    Overview[frontend/src/components/MetricsOverview.jsx] --> Metrics[Operations dashboard]
    Orchestration --> Extract
    Orchestration --> Photos
    Orchestration --> Rules
    Orchestration --> Grounding
    Rules --> Persistence
    Grounding --> Persistence
    Endpoints --> Persistence
    Queue --> Endpoints
    Evidence --> Endpoints
    Human --> Endpoints
    Metrics --> Endpoints
```

## 9. Safety Boundary

```mermaid
flowchart LR
    AI[Extraction, vision, and grounded explanation]
    Rules[Deterministic validation]
    Findings[Evidence-backed findings]
    Human[Named human handler]
    External[External authorized claims decision process]

    AI --> Rules
    Rules --> Findings
    Findings --> Human
    Human --> External
    AI -. never directly .-> External
```

The application prepares, explains, verifies, refers, and records handler actions. It does not approve, decline, pay, or allege fraud autonomously.
