

## Savings Claw
- Backend API stays in Flask.
- New SvelteKit frontend lives in `frontend/`.
- Flow:
  - connect Gmail
  - search by business/provider string
  - scan matching emails and bill attachments
  - dedupe and upload missing files/text to Hyperspell memories
  - run category-specific research
    - Exa for product price comparison
    - Google search for utility/service comparison
    - browser fallback for rides/property/product when needed
  - save research to Hyperspell
  - render savings comparison table
