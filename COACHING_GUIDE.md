# Observe Insurance Voice Agent: Coaching & Development Protocol

This document defines the strict, step-by-step coaching standard used for every step of this project.

---

## The 4-Step Standard for Every Single Part:

### Step 1: Concept, Flow & The "Why"
- Explain what problem this specific component solves.
- Explain how it fits into the broader caller-agent interaction.
- Explain why this design is necessary for a voice AI system (latency, security, speech errors).

### Step 2: Clean, Readable Code & Exact File Location
- Write clear, well-commented, straightforward Python code (no over-engineering or esoteric tricks).
- Tell the user the exact file path where the code belongs.

### Step 3: Line-by-Line / Block-by-Block Code Walkthrough
- Break down the code into easy-to-understand chunks.
- Explain what each function, parameter, and return value does in plain English.
- Highlight how errors and edge cases are handled.

### Step 4: Interview Talking Points & Trap Questions
- Provide the exact words to say to an interviewer when asked about this component.
- Cover common interviewer follow-ups (e.g., security, edge cases, scalability).

---

## Guiding Engineering Principles:
1. **Explainability Over Cleverness:** If a junior developer or interviewer cannot understand it at a glance, simplify it.
2. **Backend-Enforced Authorization:** Never rely solely on the LLM prompt for security.
3. **Fail-Safe & Graceful:** Always handle missing data, network timeouts, and bad speech input calmly without crashing.
