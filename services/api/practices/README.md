# Practice-specific extensions

Per CG11 (Coding Guidelines) and ADR 0010 (base product + per-practice
customization + upstream promotion model):

- Core modules (`app/agents/`, `app/task_engine/`, `app/books_connector/`,
  etc.) must never import from, or branch on, a specific practice.
- Practice-specific customization lives under `practices/{practice_slug}/`
  and registers itself against a defined extension point — a plugin-style
  registry, not direct monkey-patching of core modules.
- The dependency direction is one-way: `practices/` depends on `app/`,
  never the reverse.

**This directory is intentionally empty at scaffold time.** Per Dev
Readiness Checklist item OQ-07, the actual extension-point code structure
(the hook/plugin registry pattern) still needs to be concretely defined —
during or immediately after the first deployment build, once there's a
real customization to learn from, not designed in the abstract now.

Before adding anything here for a given practice, check whether it's
actually configuration (client `books_system`, service catalog pricing,
branding — all of which belong in that practice's settings/database data,
per CG4) rather than code. Most "customizations" turn out to be config
once examined properly.
