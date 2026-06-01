# PM-JAY Redesign Bundle

Everything Claude Code needs to implement the redesigned PM-JAY Assistant.

## What's in here

```
pmjay-redesign-bundle/
├── CLAUDE.md                    ← Claude Code reads this automatically
├── DESIGN_SPEC.md               ← Full design brief (read first)
├── README.md                    ← This file
└── mockup/
    └── pmjay-redesign.jsx       ← Working visual reference (single-file React)
```

## How to use this with Claude Code

1. **Drop this folder at the root of your existing PM-JAY repo** (or wherever you're working from). Claude Code will auto-load `CLAUDE.md` when it starts in that directory.

2. **Start Claude Code** in that directory:
   ```
   cd your-pmjay-repo
   claude
   ```

3. **Open with a prompt like:**
   > Read DESIGN_SPEC.md and mockup/pmjay-redesign.jsx, then implement the Ask view first. Preserve the existing SQL-generation backend and routing; only change the UI.

   Or tackle it page by page:
   > Let's start with the shell and the Discover view. Port these from the mockup into the codebase, using our existing insights API.

## Viewing the mockup yourself

`mockup/pmjay-redesign.jsx` is a complete, working React component. To see it rendered:

- **In Claude.ai**: paste it into the chat as an artifact.
- **Locally**: drop it into any React app with `lucide-react` installed. No other dependencies needed.
- **Online sandbox**: paste into a CodeSandbox / StackBlitz React template.

To toggle between states while reviewing:
- Starting mode — change `useState("ask")` near the bottom of the file (line ~520) to `"discover"` or `"track"`.
- Ask empty vs. conversation state — change `useState(false)` inside `AskView` (around line 335) to `true`.

## Design direction, in one sentence

Refined institutional — serious and trustworthy like Bloomberg Terminal, with editorial typography (Fraunces serif + Inter), a restrained ivory/ink/single-accent palette, and three consistent modes (Ask/Discover/Track) that cross-link so the product feels like one tool, not three.
