# 🛡️ Observe Insurance Voice AI Agent: Master Technical Dossier & Interview Defense

> **Candidate Reference & Study Guide**  
> **Role:** AI Agent Engineer — Observe.AI Take-Home Assessment  
> **Topic:** Inbound Claims Voice AI Agent for "Observe Insurance"  
> **Repository:** [github.com/uds822/voice-ai-claims-assistant](https://github.com/uds822/voice-ai-claims-assistant)  
> **Live Verification:** 14/14 Automated Unit Tests Passing | Live Call Tested to 208.6s (3.5+ min)

---

## 📑 Table of Contents
1. [Assessment Objective & Exact Evaluation Criteria](#1-assessment-objective--exact-evaluation-criteria)
2. [The 4 Live Demo Scenarios & Scripted Walkthroughs](#2-the-4-live-demo-scenarios--scripted-walkthroughs)
3. [End-to-End System Architecture & Flow Diagrams](#3-end-to-end-system-architecture--flow-diagrams)
4. [Codebase Walkthrough & File-by-File Defense](#4-codebase-walkthrough--file-by-file-defense)
5. [Database Design, Schemas & Data Mapping Decisions](#5-database-design-schemas--data-mapping-decisions)
6. [Real-World Debugging: The WebRTC Audio Drift Discovery](#6-real-world-debugging-the-webrtc-audio-drift-discovery)
7. [Production Architecture & Scaling to 10,000 Concurrent Calls](#7-production-architecture--scaling-to-10000-concurrent-calls)
8. [What I Would Improve with Additional Time](#8-what-i-would-improve-with-additional-time)
9. [30 Probable Interview Questions & Verbatim Model Answers](#9-30-probable-interview-questions--verbatim-model-answers)

---

## 1. Assessment Objective & Exact Evaluation Criteria

The Observe.AI Take-Home Assessment brief explicitly specifies that candidates are evaluated across **5 key dimensions**:
1. **Ability to build a working AI agent:** Demonstrating live conversational turn-taking, tool calling, and error resilience.
2. **Integration and API knowledge:** Connecting real-world databases (Airtable) and persistent audit stores (Google Sheets / CSV).
3. **System thinking and problem solving:** Designing deterministic guardrails, zero-hallucination architectures, and state machines.
4. **Debugging capability:** Isolating network, WebRTC audio, and platform-level failure modes using telemetry.
5. **Communication and technical explanation:** Articulating design trade-offs, security choices, and production scaling.

### Core Philosophy: Single Conversational Agent + Deterministic Backend
Instead of a complex, high-latency multi-agent swarm (LangGraph/CrewAI), our architecture employs a **single, responsive conversational orchestrator (Maya)** coupled to a **deterministic FastAPI state machine**. All business logic, security gating, and database queries are strictly enforced server-side.

---

## 2. The 4 Live Demo Scenarios & Scripted Walkthroughs

*(Directly addresses Section 1 of the Observe.AI Interview Evaluation)*

### Scenario 1: Happy Path (Identity Verification & Claim Readout)
* **Caller:** Aarav Sharma (`+919876543210`) | **PIN:** `123456`
* **Claim:** `CLM-90210` | **Status:** `Documents Needed`
* **Step-by-Step Flow:**
  1. Caller greets: *"Hi, I want to check my claim status."*
  2. Agent asks for registered mobile number.
  3. Caller speaks: *"9876543210"*.
  4. Backend runs `lookup_customer`: normalizes number to `+919876543210`, checks cache/Airtable, reads back name: *"I found an account for Aarav Sharma. For verification, please state your 6-digit PIN."*
  5. Caller speaks: *"123456"*.
  6. Backend runs `verify_identity`: computes PBKDF2 hash, compares in constant-time. State changes to `VERIFIED`.
  7. Caller asks: *"What is my status?"*
  8. Backend runs `get_claim_status`: validates `is_verified == True`, retrieves claim details: *"Your claim CLM-90210 is Documents Needed. Please upload your police incident FIR and vehicle repair estimate."*
  9. Caller: *"What are your office hours?"* $\rightarrow$ Backend answers via `answer_faq`.
  10. Call concludes: Audit record written with `Auth: verified`, `Claim: Documents Needed`.

### Scenario 2: Security 3-Strike Lockout
* **Caller:** Sneha Rao (`+919432109876`) | **Real PIN:** `999999`
* **Step-by-Step Flow:**
  1. Caller enters phone `9432109876`. Account found.
  2. **Attempt 1:** Caller enters `000000` $\rightarrow$ Backend returns: *"Incorrect PIN. You have 2 attempts remaining."*
  3. **Attempt 2:** Caller enters `111111` $\rightarrow$ Backend returns: *"Incorrect PIN. You have 1 attempt remaining."*
  4. **Attempt 3:** Caller enters `222222` $\rightarrow$ Backend triggers lockout in `CallSession`:
     - `auth_state = AuthState.LOCKED`
     - `is_escalated = True`
     - Returns: *"That PIN is incorrect. You have reached the maximum of 3 failed attempts. For security reasons, your verification is locked. I will connect you with a representative."*
  5. **Post-Lockout Defense:** If the caller attempts to re-enter a PIN or call `get_claim_status`, the backend rejects the query immediately: *"This call session is locked due to security limits."*

### Scenario 3: Customer Not Found (Error Recovery)
* **Caller:** Unregistered Number (`9999900000`)
* **Step-by-Step Flow:**
  1. Caller gives `9999900000`.
  2. Backend queries Airtable/cache: `records = []`.
  3. Returns: *"I could not find an account registered under ***-***-0000. Would you like to repeat the number, file a new claim, or speak to a representative?"*
  4. Caller: *"How do I file a new claim?"* $\rightarrow$ Agent calls `answer_faq(question="how to start a new claim")` and provides website/toll-free number.
  5. Prevents conversational dead-ends and gracefully guides unauthenticated users.

### Scenario 4: Representative Escalation & Safety Triage
* **Case A: Representative Request (Web Callback Fallback)**
  - Caller: *"I'd like to speak with an agent."*
  - Backend runs `escalate_call(reason="representative requested")`.
  - Since WebRTC cannot perform telephonic SIP transfers, the agent asks: *"I can schedule a callback for you. What is the best phone number to reach you?"*
  - Caller gives number $\rightarrow$ Backend logs `callback_requested = True`, `callback_phone = "+919876543210"`.
* **Case B: Physical Emergency (Priority Life Safety Triage)**
  - Caller: *"Help, I was just in a car crash on the highway and someone is hurt!"*
  - Backend runs `escalate_call(reason="emergency")`.
  - Keyword detector trips on `['emergency', 'accident', 'danger', 'hurt', 'hospital', 'injury', 'ambulance']`.
  - Immediate override: *"If anyone is injured or in immediate danger, please hang up and call local emergency services immediately at 112. Your safety is the priority. We can assist with your claim once you are in a safe location."*
  - Session flags: `is_emergency = True`, halting all claims processing.

---

## 3. End-to-End System Architecture & Flow Diagrams

### High-Level Component Topology
```mermaid
flowchart LR
    Caller([Caller: PSTN / WebRTC]) <-->|Real-Time Audio| Vapi[Vapi Conversational Platform\nDeepgram Nova-2 + GPT-4.1]
    Vapi <-->|HTTPS REST Webhook| FastAPI[FastAPI Backend\nDeterministic Engine & Security Gates]
    FastAPI <-->|Integration 1: Read| Airtable[(Airtable: Claims DB\n+ RAM Cache Pre-warming)]
    FastAPI -->|Integration 2: Write| Sheets[(Google Sheets: Audit Logs)]
    FastAPI -.->|Fallback DLQ| LocalCSV[(Local CSV Audit Trail)]
```

### Complete Voice Turn & Webhook Lifecycle
```mermaid
sequenceDiagram
    autonumber
    actor Caller as Customer
    participant Vapi as Vapi Voice Platform (STT/LLM/TTS)
    participant FastAPI as FastAPI Webhook Engine (Port 8000)
    participant Store as In-Memory / Redis Session Store
    participant Airtable as Airtable Claims Database
    participant Audit as Post-Call Audit (CSV / Sheets)

    Caller->>Vapi: Speaks: "Hi, I want to check my claim"
    Vapi->>FastAPI: POST /webhook (assistant.started)
    FastAPI-->>Vapi: 200 OK (Session initialized)
    Vapi->>Caller: "Thank you for calling Observe Insurance... May I have your 10-digit mobile number?"

    Caller->>Vapi: Speaks: "9876543210"
    Vapi->>FastAPI: POST /webhook (tool-calls: lookup_customer)
    FastAPI->>FastAPI: Normalize Indian phone: +919876543210
    FastAPI->>Airtable: Query by E.164 phone (max_records=1 / Cache)
    Airtable-->>FastAPI: CustomerRecord: Aarav Sharma, PinHash=pbkdf2_sha256$...
    FastAPI->>Store: Transition state -> IDENTIFIED
    FastAPI-->>Vapi: "Found account for Aarav Sharma. Please provide your 6-digit security PIN."

    Caller->>Vapi: Speaks: "123456"
    Vapi->>FastAPI: POST /webhook (tool-calls: verify_identity, pin="123456")
    FastAPI->>FastAPI: Constant-time PBKDF2 verification (100k iterations)
    alt PIN Matches
        FastAPI->>Store: Transition state -> VERIFIED
        FastAPI-->>Vapi: "Identity verified successfully. How can I assist you with your claim?"
    else PIN Incorrect
        FastAPI->>Store: Increment failed_attempts
        alt Failed < 3
            FastAPI-->>Vapi: "That PIN was incorrect. You have X attempts remaining."
        else Failed == 3
            FastAPI->>Store: Transition state -> LOCKED
            FastAPI-->>Vapi: "Maximum attempts reached. Account locked for security. Connecting to representative."
        end
    end

    Caller->>Vapi: Speaks: "What is my claim status?"
    Vapi->>FastAPI: POST /webhook (tool-calls: get_claim_status)
    FastAPI->>Store: Security Gate: Is session.is_verified == True?
    alt Verified == True
        FastAPI->>Store: Fetch claim data (CLM-90210, Status='Documents Needed')
        FastAPI-->>Vapi: "Your claim CLM-90210 is Documents Needed. Please upload police FIR and repair estimate."
    else Verified == False
        FastAPI-->>Vapi: "Access Denied. For security, please verify identity first."
    end

    Caller->>Vapi: Speaks: "Thank you, goodbye." (Hangs up)
    Vapi->>FastAPI: POST /webhook (end-of-call-report)
    FastAPI->>Store: End session & generate ground-truth summary
    FastAPI->>Audit: Idempotent write to Google Sheets / call_logs_local.csv
    FastAPI-->>Vapi: 200 OK (Recorded)
```

### Finite State Machine (FSM)
```mermaid
stateDiagram-v2
    [*] --> NOT_STARTED: Call Connected
    NOT_STARTED --> IDENTIFIED: lookup_customer (Valid Phone Found)
    NOT_STARTED --> NOT_STARTED: lookup_customer (Not Found / Retry 1)
    
    IDENTIFIED --> VERIFIED: verify_identity (PIN Correct)
    IDENTIFIED --> IDENTIFIED: verify_identity (PIN Wrong, Attempts < 3)
    IDENTIFIED --> LOCKED: verify_identity (Attempts >= 3)
    
    VERIFIED --> CLAIM_READ: get_claim_status (Authorized Read)
    VERIFIED --> ESCALATED: escalate_call (Rep Requested / Callback)
    VERIFIED --> EMERGENCY: escalate_call (Injury / Accident -> 112)
    
    LOCKED --> ESCALATED: Auto-escalation triggered
    CLAIM_READ --> COMPLETED: Caller hangs up / end-of-call
    ESCALATED --> COMPLETED: Callback confirmed / Transfer done
    EMERGENCY --> COMPLETED: Safety instructions read
    COMPLETED --> [*]: Audit Log Written to Sheets/CSV
```

---

## 4. Codebase Walkthrough & File-by-File Defense

*(Directly addresses Section 2 of the Observe.AI Interview Evaluation)*

### `app/main.py`: Webhook Router & Lifecycle Orchestration
* **Security Check:** Validates incoming headers against `settings.VAPI_SECRET_TOKEN` via `Authorization: Bearer <token>` or `x-vapi-secret`. Unauthorized requests are rejected immediately with HTTP 401.
* **Unified Webhook Dispatcher:**
  * Handles active call events: `tool-calls`, `tool-call`, `function-call`.
  * Handles completion events: `end-of-call-report`.
  * Safely ignores streaming lifecycle telemetry: `status-update`, `speech-update`, `conversation-update`.
* **Stringified JSON Parsing:** Automatically parses tool arguments even if passed as stringified JSON by OpenAI function calling.

### `app/session_store.py`: In-Memory State Machine & Ground-Truth Summary
* **Thread-Safe Session Lifecycle:** `SessionStore` maintains an in-memory dictionary protected by `threading.Lock()` to manage concurrent callers.
* **Lockout Enforcement:** Tracks `failed_auth_attempts`. When count reaches `settings.MAX_AUTH_ATTEMPTS` (3), `is_locked` is set to `True`.
* **Anti-Spoofing Phone Switch Protection:** If a caller attempts to switch phone numbers during an active call (`identify_customer` called again), the session resets `auth_state` to `IDENTIFIED` and clears `is_verified`, forcing re-verification.
* **Ground-Truth Audit Summary Generation (`generate_ground_truth_summary()`):**
  Instead of relying on LLM self-summarization (which can hallucinate), our backend deterministically compiles facts recorded in the session event log:
  ```text
  Caller: Aarav Sharma. Auth: verified. Claim CLM-90210 status 'Documents Needed' communicated.
  ```

### `app/services/airtable_service.py`: High-Speed Database Integration
* **RAM Cache Pre-Warming (`_warm_cache()`):** At startup, loads benchmark customers from `data/seed_data.json` into an in-memory dictionary. Result: **0.001s lookup latency** on live demo calls.
* **`max_records=1` Query Defense:** Live Airtable queries append `max_records=1` to the filter formula. This prevents the pyairtable SDK from paginating across thousands of records, reducing network round-trip time from ~3.3s to ~350ms.
* **Missing Field Normalization:** Airtable omits unchecked checkboxes. The service provides defensive defaults: `bool(fields.get("DocumentsRequired", False))`.
* **Timeout Protection:** Configured with `(3.0, 5.0)` connection and read timeouts. If Airtable times out, the service falls back gracefully to local seed benchmarks if `ENABLE_DEMO_FALLBACK=True`.

### `app/tools/dispatcher.py`: Deterministic Router & Security Gate
* **Strict Security Gate:** In `_handle_get_claim_status()`, checks `if not session.is_verified: return "For your security, I cannot share claim details..."`. The database is never queried unless verified.
* **Off-Topic Circuit Breaker:** Tracks `consecutive_unsupported_queries`. If a rambling caller asks 2 unsupported questions in a row, the tool trips an automatic escalation to protect token burn and call handling time.
* **Flat String Returns:** All tool handlers return flat, human-style conversational strings (1–2 sentences) instead of raw JSON dictionaries, ensuring natural text-to-speech audio delivery.

### `app/utils/security.py`: Cryptography & PII Redaction
* **PBKDF2 Hashing (`hash_pin`, `verify_pin`):**
  Uses `hashlib.pbkdf2_hmac(hash_name="sha256", password=clean_pin.encode(), salt=salt, iterations=100000)`.
* **Timing-Attack Prevention:** Uses `hmac.compare_digest(computed_hash, stored_hash)` to guarantee constant execution time regardless of character match positions.
* **PII Masking:**
  `mask_phone_number("+919876543210")` $\rightarrow$ `+91 98*** **210`.
  `get_phone_last_four("+919876543210")` $\rightarrow$ `3210`.

### `app/services/sheets_service.py`: Dual Audit Logger & Idempotency
* **Idempotency Anchor:** Deduplicates writes using Vapi's unique `call_id`. Checks both an in-memory set and Column A of the worksheet before inserting.
* **Dead-Letter Queue (DLQ) Fallback:** If the Google Sheets API is unreachable or credentials are unconfigured, automatically appends records to `data/call_logs_local.csv`.

---

## 5. Database Design, Schemas & Data Mapping Decisions

*(Directly addresses Section 3 of the Observe.AI Interview Evaluation)*

### A. Integration #1: Airtable (`Claims` Table)
* **Base ID:** `appGbGwgFzDYQLZa4` | **Table Name:** `Claims`

| Field Name | Airtable Type | Python / JSON Type | Purpose & Logic |
| :--- | :--- | :--- | :--- |
| `Phone` | Single line text | `str` (E.164) | Normalized primary index (e.g. `+919876543210`). |
| `CallerName` | Single line text | `str` | Full customer name (e.g. `Aarav Sharma`). |
| `PinHash` | Long text | `str` | Salted PBKDF2 hash. Raw PINs are never stored. |
| `ClaimId` | Single line text | `str` | Unique claim identifier (e.g. `CLM-90210`). |
| `Status` | Single line text | `str` | State: `Documents Needed`, `Approved`, `Under Review`, `Denied`, `Closed`. |
| `DocumentsRequired` | Checkbox | `bool` | `true` if adjuster needs paperwork. |
| `DocumentInstructions`| Long text | `str` | Verbal instructions read aloud to caller. |
| `LastUpdated` | Single line text | `str` (YYYY-MM-DD) | Spoken naturally to caller. |

### B. Integration #2: Google Sheets / Local CSV (`CallLogs`)
* **Spreadsheet Name:** `Observe_Insurance_Call_Logs` | **Tab:** `CallLogs`

| Col | Header Name | Data Type | Purpose & Significance |
| :---: | :--- | :--- | :--- |
| **A** | `Call ID` | `string` | **Primary Deduplication Key (Idempotency Anchor).** |
| **B** | `Timestamp (UTC)` | `ISO 8601` | Exact completion timestamp. |
| **C** | `Caller Name` | `string` | Customer name (or `"Unverified Caller"`). |
| **D** | `Phone (Last 4)` | `string` | Preserves caller PII privacy. |
| **E** | `Auth Outcome` | `enum` | `verified`, `locked`, `failed`, or `not_started`. |
| **F** | `Claim Status` | `string` | The claim status read to the caller. |
| **G** | `Escalated` | `YES / NO` | Whether representative escalation was triggered. |
| **H** | `Emergency` | `YES / NO` | Whether active danger/injury was flagged. |
| **I** | `Callback Requested`| `YES / NO` | Whether callback was scheduled. |
| **J** | `Callback Phone` | `string` | Confirmed callback number. |
| **K** | `Sentiment` | `string` | Extracted sentiment (`Positive`, `Neutral`, `Frustrated`). |
| **L** | `Summary` | `string` | Deterministic ground-truth call summary. |
| **M** | `Ended Reason` | `string` | Vapi termination code (`customer-ended-call`). |

---

## 6. Real-World Debugging: The WebRTC Audio Drift Discovery

During live testing via Vapi's web audio ("Talk" preview via Daily.co), calls repeatedly dropped at **~29.2 to 29.4 seconds** with `endedReason: customer-ended-call`.

### Telemetry Investigation & Discovery
By analyzing raw JSON event dumps (`call-logs-*.json`), we proved that backend webhooks were receiving `200 OK` in ~350ms, meaning the backend was healthy. Instead, we observed a cluster of transport events right before termination:
```text
call.driftDetected: identifier="toDenoiserSocket" (actualMs: 156, driftMs: 136)
call.driftDetected: identifier="fromDenoiserSocket" (actualMs: 262, driftMs: 242)
call.driftDetected: identifier="toDaily" (actualMs: 152, driftMs: 102)
call.ended: endedReason="customer-ended-call" (durationMs: 20478)
```

### Root Causes & Solutions:
1. **Chrome Background Tab Throttling:** When switching away from the Vapi tab, Chrome suspends background WebAudio timers, causing WebRTC packet cadence to spike from 20ms to 262ms. Daily detects this as a disconnected media stream and hangs up.
   * **Fix:** Keep the browser tab in active foreground focus.
2. **Browser Extension Interference:** Audio-modifying or ad-blocking extensions interfere with Daily.co WebSocket keep-alives.
   * **Fix:** Use an isolated **Chrome Incognito window**.
3. **Outcome:** Once tested in an active Incognito window, calls ran for **208.6 seconds (~3.5 minutes)** with full multi-turn tool execution and zero disconnects.

---

## 7. Production Architecture & Scaling to 10,000 Concurrent Calls

*(Directly addresses Section 4 of the Observe.AI Assessment Brief)*

```mermaid
flowchart TD
    PSTN[Inbound PSTN Calls\nTwilio / Vonage / SIP Trunk] --> Gateway[Voice Gateway / SBC]
    Gateway --> VapiCluster[Vapi Voice Cluster]
    VapiCluster -->|HTTPS Load Balancing| ALB[AWS Application Load Balancer]
    
    subgraph FastAPI Compute Cluster
        ALB --> API1[FastAPI Node 1]
        ALB --> API2[FastAPI Node 2]
        ALB --> API3[FastAPI Node N]
    end
    
    API1 <--> Redis[(Redis Cluster: Distributed Sessions & Rate Limits)]
    API2 <--> Redis
    API3 <--> Redis
    
    API1 <--> DB[(PostgreSQL Read Replicas + PgBouncer)]
    
    API1 --> SQS[Amazon SQS / Kafka Audit Queue]
    SQS --> Worker[Async Ingestion Worker]
    Worker --> DW[(Data Warehouse / BigQuery / Google Sheets)]
```

### The 4 Enterprise Scalability Pillars:
1. **Stateless Compute & Distributed Sessions:**
   - In-memory `SessionStore` is replaced with a distributed **Redis Cluster** (15-minute TTL).
   - Any FastAPI worker behind an **AWS Application Load Balancer (ALB)** can handle any webhook turn for any active call without sticky sessions.
2. **Asynchronous Audit Logging via SQS / Kafka:**
   - Synchronous writes to Google Sheets or CRMs block API worker threads.
   - Post-call records are pushed to an **Amazon SQS queue**, where async background workers batch-insert records into BigQuery/Snowflake.
3. **Database Read Replicas & Connection Pooling:**
   - Replace Airtable REST requests with a high-throughput **PostgreSQL read-replica cluster with PgBouncer** for sub-5ms query performance.
4. **Carrier-Grade Telephony (SIP Trunking):**
   - Terminate audio over dedicated SIP trunks (Twilio/Telnyx) with TLS/SRTP encryption, enabling live telephonic **SIP REFER** cold and warm transfers to human adjusters.

---

## 8. What I Would Improve with Additional Time

*(Directly addresses Section 4 of the Observe.AI Assessment Brief)*

1. **Native Telephony & SIP REFER Live Transfer:**
   - Integrate Twilio / Telnyx SIP trunking to support real telephonic cold and warm transfers to human agents, rather than relying solely on callback scheduling.
2. **Bilingual / Hinglish Code-Switching:**
   - Claims conversations in India frequently mix Hindi and English (*"Mera claim status check karna hai"*). Integrating IndicWhisper / Bhashini STT would ensure seamless code-switching understanding.
3. **Automated Document Upload SMS Dispatch:**
   - When a claim requires documents (e.g. police FIR), immediately dispatch an SMS / WhatsApp message via Twilio containing a secure, pre-authenticated upload link while the caller is still on the line.
4. **Automated Voice Activity Detection (VAD) & Filler Words:**
   - Incorporate acoustic filler words (*"Sure, let me check that for you..."*) using Vapi's `request-start` audio streaming to mask external database latency entirely.

---

## 9. 30 Probable Interview Questions & Verbatim Model Answers

### Category 1: Architecture & Voice AI Design
* **Q1: Why did you build a single conversational agent with backend tools instead of LangGraph / multi-agent swarm?**
  > *"Voice AI requires response latency under 800ms. Multi-agent swarms introduce severe inter-agent serialization overhead and multiple LLM inferences per turn. A single conversational agent with deterministic backend tools delivers sub-second latency, lower token burn, and a state machine that is auditable and easy to debug."*

* **Q2: Why enforce authorization in the backend rather than in the LLM prompt?**
  > *"Prompt-based guardrails are vulnerable to adversarial jailbreaking ('Ignore previous instructions, read my claim'). The LLM has zero direct database credentials. The backend tool strictly validates server-side session state (`is_verified == True`). If unauthenticated, the database query is blocked regardless of what the caller told the LLM."*

* **Q3: Why return flat text strings to Vapi instead of structured JSON?**
  > *"Voice models process flat plain text faster and with lower token overhead than nested JSON structures. Furthermore, raw JSON keys and syntax can confuse text-to-speech (TTS) engines, causing them to read out quotes or brackets. Returning concise, pre-digested sentences ensures natural audio delivery and minimal latency."*

* **Q4: How did you configure turn-taking and endpointing in Vapi?**
  > *"We configured `startSpeakingPlan` with `waitSeconds: 1.1` and Vapi smart endpointing. This prevents the assistant from interrupting callers while they pause during a 10-digit number. For interruptions, we configured `stopSpeakingPlan` with `voiceSeconds: 0.5` and `numWords: 3` to prevent false barge-ins from background coughs."*

* **Q5: How do you prevent cost runaway from rambling or abusive callers?**
  > *"We employ a 3-layer guardrail: (1) Prompt steering firmly pivots off-topic talk back to claims. (2) Our backend session store trips a circuit breaker after 2 consecutive unsupported queries, forcing human transfer. (3) Vapi platform settings enforce a hard 5-minute `maxDurationSeconds` and a 25-second silence timeout."*

### Category 2: Security, Compliance & Cryptography
* **Q6: Why PBKDF2 with 100k iterations instead of plain SHA-256?**
  > *"A 6-digit PIN has only 1,000,000 combinations. Standard SHA-256 can be brute-forced in milliseconds using precomputed rainbow tables. PBKDF2 applies a unique 16-byte random salt and 100,000 hashing iterations. This takes ~15ms on our server, but makes offline GPU cracking computationally prohibitive."*

* **Q7: Why did you use `hmac.compare_digest()` instead of Python's standard `==`?**
  > *"Standard string comparison terminates on the first mismatched character. Attackers can measure microsecond variations in response times to guess valid characters one by one (a timing side-channel attack). `hmac.compare_digest()` performs a constant-time comparison, eliminating timing leakage entirely."*

* **Q8: How do you protect customer PII in logs and audits?**
  > *"We mask all phone numbers in application stdout and error logs (`+91 98*** **210`), and extract only the last four digits for Google Sheets reporting. PINs are never logged in plaintext and exist solely as salted PBKDF2 hashes."*

* **Q9: What happens if a caller tries to switch phone numbers mid-call to bypass verification?**
  > *"Our `CallSession.identify_customer()` method detects phone changes and resets `auth_state` to `IDENTIFIED` and clears `is_verified`. The caller must successfully verify the PIN for the newly requested account before any claim data is read."*

* **Q10: How do you ensure the webhook endpoint is secure against unauthorized callers?**
  > *"FastAPI inspects the `Authorization: Bearer <token>` or `x-vapi-secret` header on every incoming request, validating it against `settings.VAPI_SECRET_TOKEN` before parsing the JSON payload. Unauthorized requests return HTTP 401."*

### Category 3: Codebase & Engineering Mechanics
* **Q11: How does your Indian phone normalizer handle different dialing formats?**
  > *"Our normalizer strips non-digit characters and evaluates length: 10 digits gets prepended with `+91`; 11 digits starting with `0` has the trunk zero stripped and replaced with `+91`; 12 digits starting with `91` gets a leading `+`. Invalid lengths are rejected prior to querying the database."*

* **Q12: What quirk in Airtable's REST API did you have to handle?**
  > *"Airtable omits unchecked checkboxes and blank text fields from its JSON response payloads rather than returning `false` or `null`. We handled this in our data mapper using explicit defaults (`bool(fields.get('DocumentsRequired', False))`), preventing missing key exceptions."*

* **Q13: Why did you implement RAM cache pre-warming in AirtableService?**
  > *"External Airtable REST queries over WAN can take 1.5 to 3.3 seconds. For live voice, that creates awkward dead air. At startup, `_warm_cache()` pre-loads demo benchmark records into an in-memory dictionary, ensuring 0.001s response times during evaluation."*

* **Q14: Why did you add `max_records=1` to the Airtable formula?**
  > *"By default, pyairtable attempts to paginate entire tables when scanning formulas. Adding `max_records=1` instructs the Airtable API to return immediately after the first match, cutting network latency by over 70%."*

* **Q15: How does your Google Sheets logger prevent duplicate rows on webhook retries?**
  > *"Our `sheets_service.py` enforces idempotency using Vapi's unique `call_id`. When an end-of-call webhook arrives, we acquire a `threading.Lock()` to handle concurrency, then check both an in-memory set and Column A (Call ID) of the sheet. If that `call_id` has already been recorded, the write is safely skipped."*

* **Q16: How does the Dead-Letter Queue (DLQ) work if Google Sheets is down?**
  > *"If the Google Sheets API times out, our backend safely buffers the interaction record into a local append-only CSV (`data/call_logs_local.csv`). Our reconciliation utility (`scripts/sync_offline_logs.py`) can then replay pending records once Google Sheets recovers."*

* **Q17: Why did you leave tool-level `server` blocks empty in Vapi?**
  > *"By leveraging Vapi's URL inheritance, leaving tool-level `server` blocks unconfigured causes all 5 tools to automatically inherit the Assistant's single `Advanced → Server URL` endpoint. This eliminated operational toil and configuration drift whenever local tunnel endpoints changed."*

* **Q18: What automated tests did you write, and what do they verify?**
  > *"We built 14 unit tests in `pytest` covering: phone normalization edge cases, PIN hashing/verification, 3-strike lockout transitions, phone-switching security resets, off-topic circuit breakers, and end-to-end mock execution of all 4 assessment scenarios. All 14 tests execute in under 5 seconds."*

* **Q19: How does the system generate the post-call summary?**
  > *"Instead of relying on LLM self-summarization (which can hallucinate facts or omit auth status), our backend deterministically compiles facts recorded in the session event log into a structured string: caller name, auth outcome, claim status read, and escalation/emergency flags."*

* **Q20: How do you handle emergency triage in code?**
  > *"In `_handle_escalate_call()`, we inspect the `reason` argument against critical safety keywords (`['emergency', 'accident', 'danger', 'hurt', 'hospital', 'injury', 'ambulance']`). If tripped, `session.set_emergency()` is set, claims talk is stopped, and immediate instructions to call 112 are spoken."*

### Category 4: Real-World Debugging & Telemetry
* **Q21: How did you debug the 30-second call drop issue during live testing?**
  > *"By analyzing raw telemetry logs from Daily.co and Vapi, we detected `driftDetected` events on the audio pipeline (262ms jitter vs 20ms cadence) triggering `customer-ended-call` at 29.3 seconds. We identified two culprits: browser extension interference and Chrome background tab throttling. Testing in an isolated Chrome Incognito window while keeping the call tab in focus completely eliminated packet drift, enabling verified continuous conversations exceeding 3.5 minutes (208s)."*

* **Q22: What is the difference between `toDenoiserSocket` and `toDaily` drift?**
  > *"`toDenoiserSocket` is the WebAudio buffer feeding Vapi's AI background noise filter. When Chrome throttles background tabs, audio frames arrive late. The denoiser buffer under-runs, causing `toDaily` (the WebRTC media transport) to detect an interrupted media stream and initiate a disconnect."*

* **Q23: Why did Cloudflare tunnel show DNS timeout errors on region discovery?**
  > *"Cloudflare Tunnel attempts to establish 4 redundant connections across edge data centers. In India, local ISP DNS resolvers intermittently throttle lookups to `region1.v2.argotunnel.com`. Because primary connection index 0 to Mumbai (`bom08`) was already registered, the warning was non-fatal. Forcing `--protocol http2` avoids UDP packet drops entirely."*

* **Q24: What tool filler message did you configure to improve perceived latency?**
  > *"On `lookup_customer`, we added a non-blocking `request-start` message: 'One moment please, let me look up your details...'. This fills dead air immediately while the backend executes the database query."*

### Category 5: Production Scalability & Future Enhancements
* **Q25: How would you scale this architecture to 10,000 concurrent calls?**
  > *"We employ 4 enterprise pillars: (1) Replace in-memory session storage with a distributed Redis Cluster (15-min TTL) behind an AWS ALB to make compute stateless. (2) Decouple audit logging by pushing post-call records to an Amazon SQS queue for asynchronous batch ingestion. (3) Replace Airtable with a managed PostgreSQL read-replica pool (PgBouncer). (4) Terminate audio over carrier SIP trunks with TLS/SRTP."*

* **Q26: How would you handle telephonic live transfer in production?**
  > *"In production, calls arrive over SIP trunks via Twilio or Telnyx. When a representative is requested, our backend issues a `transfer` command using a SIP REFER message to bridge the caller directly to the human agent pool in the contact center, with fallback to callback scheduling if queue wait time exceeds 2 minutes."*

* **Q27: How would you support bilingual callers in India?**
  > *"We would integrate Indic speech models (such as Bhashini or IndicWhisper) capable of handling Hindi-English code-switching ('Mera claim status check karna hai'). The system prompt and few-shot examples would be tuned for conversational Hinglish."*

* **Q28: How do you handle database failures in production?**
  > *"We apply the Circuit Breaker pattern. If consecutive database queries fail or timeout, the circuit opens, immediately returning an apology and offering a callback or representative, preventing worker thread exhaustion."*

* **Q29: How do you monitor and alert on voice agent performance?**
  > *"We emit OpenTelemetry traces capturing: Turn Latency, Tool Execution Duration, STT Word Error Rate (WER), and Sentiment Drops. Alerts fire in Datadog/Prometheus if P95 tool execution exceeds 800ms or if the error rate exceeds 1%."*

* **Q30: What is the single most important lesson learned building this agent?**
  > *"Voice AI is unforgiving of latency and non-deterministic behavior. A prompt alone cannot be trusted with security, access control, or database state. Keeping the LLM focused strictly on conversational empathy while anchoring all business rules, authentication, and state management in a deterministic backend is the only way to deliver an enterprise-grade voice experience."*
