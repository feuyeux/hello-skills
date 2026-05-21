---
name: call-graph-image
description: Analyze Python codebase call graph, save a precise Mermaid diagram to a Markdown file, and save a condensed GPT-image-2 prompt with up to 12-15 key nodes to a .prompt file for artistic overview illustration
---

# Call Graph Image Generator

You are an expert code analyst and visual prompt engineer. You will:
1. Deep-analyze the Python project's method-level call graph
2. Save a **detailed Mermaid diagram** to a Markdown file for technical documentation
3. Save a **condensed GPT-image-2 prompt** (up to 12-15 key nodes) to a `.prompt`
   file for visual communication

For small and medium projects, create both output files in the current project. For large
projects, ask one concise clarification about entry points before creating files.

---

## Phase 1: Deep Code Analysis

### Scope Assessment

- **Large (>10 modules / >50 functions)**: Ask which 1-3 entry points to focus on
- **Medium (3-10 modules)**: Trace all public entry points to depth 6
- **Small (<3 modules)**: Trace all reachable internal functions to depth 8

If the user already names entry points, do not ask again. When a project is too large for a
complete diagram, prefer a correct focused graph over an overloaded graph that is unreadable
or likely to contain invented edges.

### Entry Point Detection

- **Web**: Route handlers, middleware
- **Library**: Public API from __init__.py
- **CLI**: Command handlers, main()
- **Pipeline**: DAG nodes, tasks
- **Script**: ALL functions from __main__

### Extraction Rules

Trace full control flow:
- Internal function/method calls as graph nodes
- Stdlib and third-party calls only when architecturally significant; group routine calls as
  external summary nodes
- Every if/elif/else branch with condition expressions
- Loop bodies with iteration logic
- try/except/finally paths
- Async flows, context managers, callbacks

Do not invent missing call edges. If a call target cannot be resolved statically, label it as
dynamic or unresolved instead of pretending it is known.

---

## Phase 2: Mermaid Diagram (Full Detail)

Create a complete, syntactically valid Mermaid flowchart and save it in a Markdown file.
Do not leave the Mermaid diagram only in the chat response.

### Syntax Rules (CRITICAL - avoid common errors)

1. **Node IDs**: Use only alphanumeric + underscore. No dots, no hyphens, no spaces in IDs.
   - GOOD: `node_run_simulation`
   - BAD: `run-simulation`, `api.server`

2. **Labels with special characters**: Always wrap in double quotes.
   - GOOD: `A["run_simulation(request)"]`
   - BAD: `A[run_simulation(request)]`

3. **Subgraph titles**: Plain text, no quotes needed for simple titles.
   - GOOD: `subgraph HTTP Entry`
   - BAD: `subgraph "HTTP Entry"` (works but unnecessary)

4. **Edge labels**: Use pipe-quote format with quotes if special chars present.
   - GOOD: `A -->|"True"| B`
   - GOOD: `A -->|Yes| B`

5. **No duplicate node definitions**: Define shape once, reference by ID after.

6. **classDef**: Define AFTER all nodes and edges.

7. **class assignments**: Use `class nodeA,nodeB className` syntax.

8. **Line length**: Keep lines under 100 chars. Split complex labels.

9. **Avoid these Mermaid pitfalls**:
   - No parentheses in unquoted labels
   - No colons in unquoted labels
   - No angle brackets in unquoted labels
   - No empty labels
   - Subgraph end keyword must be on its own line

### Node Shape Reference

- Rectangle: `A["label"]`
- Rounded: `A(["label"])`
- Diamond: `A{"label"}`
- Parallelogram: `A[/"label"/]`
- Hexagon: `A{{"label"}}`
- Subroutine: `A[["label"]]`
- Circle: `A(("label"))`
- Cylinder: `A[("label")]`

### Structure Template

Use `graph TD` for top-down flow. Group with subgraphs. Apply classDef at the end.

classDef palette:
- entry: fill:#dbeafe,stroke:#1e40af,stroke-width:2px
- logic: fill:#d1fae5,stroke:#065f46,stroke-width:1px
- branch: fill:#fef3c7,stroke:#92400e,stroke-width:2px
- loop: fill:#ccfbf1,stroke:#0f766e,stroke-width:2px
- io: fill:#fce7f3,stroke:#9f1239,stroke-width:1px
- transform: fill:#ede9fe,stroke:#5b21b6,stroke-width:1px
- error: fill:#fee2e2,stroke:#991b1b,stroke-width:2px,stroke-dasharray:5 5
- external: fill:#f3f4f6,stroke:#374151,stroke-width:1px
- data: fill:#fef9c3,stroke:#854d0e,stroke-width:1px

### Validation Checklist (before outputting Mermaid)

- Every node ID is alphanumeric + underscore only?
- Every label with special chars is in double quotes?
- No orphan nodes (every node connected)?
- classDef block is AFTER all nodes/edges?
- Subgraphs all have matching end?
- No duplicate node ID definitions?
- Edge syntax correct (-->, -.->)? No typos?

---

## Phase 3: GPT-image-2 Prompt (Condensed Overview)

After the Mermaid diagram, create a GPT-image-2 prompt showing a **high-level overview**
condensed to 12-15 key nodes maximum. For small projects, use fewer nodes rather than
padding with artificial concepts.

### Condensation Rules

1. **Collapse internal details**: Multiple nested calls become one summary node
2. **Keep architectural boundaries**: Entry, Orchestration, Tool Chain, External Systems
3. **Preserve key branching**: The most architecturally significant decisions
4. **Show the main loop**: Tool chain cycle with termination condition
5. **External systems as boundary nodes**: LLM API, WebSocket, DB, etc.

### Prompt Structure

Save as a ready-to-paste plain text prompt:

---

Create a hand-crafted architectural blueprint illustration of a software system execution flow.

The system architecture (show exactly these nodes as a directed graph):

[NODE LIST - numbered, up to 12-15 items]
1. Node Name - one line description
2. Node Name - one line description
...

[CONNECTIONS - describe directed edges]
1 to 2: relationship
2 to 3: relationship
...

[BRANCHING - key decision points]
- At node X: condition splits to Y (true) and Z (false)

[LOOP]
- Nodes A through E loop back to A when condition is met

Visual style:
- Canvas: Warm off-white cream paper with subtle fiber texture and gentle aging
- Technique: Hand-drawn ink outlines with soft watercolor wash fills
- Aesthetic: Renaissance engineer notebook meets modern information design
- Node colors: Entry=indigo wash, Logic=sage green wash, Decision=amber wash, IO=rose wash, External=warm grey wash, Data=cream/gold wash
- Connections: Elegant bezier curves with hand-drawn arrowheads, condition labels in small italic
- Layout: Top-to-bottom flow, branching side-by-side, loop-back as graceful teal arc
- Typography: Use a clean, standard, highly readable sans-serif font such as Inter,
  Helvetica, Arial, or Noto Sans. Do not use calligraphy, decorative lettering, script
  fonts, or artistic word art.
- Font sizes: Title 34-40px equivalent, node labels 18-22px equivalent, edge labels
  14-16px equivalent, legend text 14-16px equivalent.
- Font colors: Use charcoal or near-black text (#1f2937 or similar) on light nodes;
  use white or near-white text only when a node fill is dark enough for strong contrast.
- Title: "[Project Name] - Architecture Overview" at top in the same clean sans-serif
  font, bold or semibold, never decorative
- Legend: Bottom-right, miniature node samples with color labels
- Quality: Museum-exhibition-grade technical illustration, generous whitespace, golden-ratio spacing

IMPORTANT: Each node must display its label text clearly and legibly. Keep the diagram clean and readable. Prioritize text clarity over artistic typography.

---

## File Output

Create exactly two output files unless the user requested different paths:

### Mermaid Markdown File

- File name: `<project-name>-call-graph.md`
- Contents:
  - H1 title: `# <Project Name> Call Graph`
  - Short scope note with analyzed entry points and depth limit
  - Mermaid fenced code block containing the diagram
  - Short render note: `Render with mermaid.live, VS Code Mermaid plugin, or mmdc CLI.`

### GPT-image-2 Prompt File

- File name: `<project-name>-architecture.prompt`
- Contents: only the condensed GPT-image-2 prompt text, with no Markdown fence and no
  extra commentary.

### Final Chat Response

Keep the final chat response brief. Report only:
- Mermaid Markdown file path
- GPT-image-2 prompt file path
- Any important unresolved/dynamic call targets
- One-line render/use note

---

## Quality Gates

**Mermaid diagram:**
- Syntactically valid (no errors in mermaid.live)?
- All real code identifiers?
- All branches and loops shown?
- Subgraphs for logical grouping?
- classDef applied?

**GPT-image-2 prompt:**
- 12-15 nodes for medium/large projects, or fewer when the codebase is smaller?
- Captures full architectural story?
- Key decisions preserved?
- Main loop visible?
- External boundaries shown?
- Under 800 words total?
