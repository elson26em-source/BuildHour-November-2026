---
name: Obsidian Aurum
colors:
  surface: '#121318'
  surface-dim: '#121318'
  surface-bright: '#38393f'
  surface-container-lowest: '#0d0e13'
  surface-container-low: '#1a1b21'
  surface-container: '#1e1f25'
  surface-container-high: '#292a2f'
  surface-container-highest: '#34343a'
  on-surface: '#e3e1e9'
  on-surface-variant: '#d1c6ab'
  inverse-surface: '#e3e1e9'
  inverse-on-surface: '#2f3036'
  outline: '#9a9078'
  outline-variant: '#4d4632'
  surface-tint: '#eec200'
  primary: '#ffecb9'
  on-primary: '#3c2f00'
  primary-container: '#facc15'
  on-primary-container: '#6c5700'
  inverse-primary: '#735c00'
  secondary: '#ddb8ff'
  on-secondary: '#490080'
  secondary-container: '#7c03d3'
  on-secondary-container: '#dfbcff'
  tertiary: '#ffeacf'
  on-tertiary: '#442c00'
  tertiary-container: '#ffc772'
  on-tertiary-container: '#795100'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#ffe083'
  primary-fixed-dim: '#eec200'
  on-primary-fixed: '#231b00'
  on-primary-fixed-variant: '#574500'
  secondary-fixed: '#f0dbff'
  secondary-fixed-dim: '#ddb8ff'
  on-secondary-fixed: '#2c0051'
  on-secondary-fixed-variant: '#6800b4'
  tertiary-fixed: '#ffddb0'
  tertiary-fixed-dim: '#ffba46'
  on-tertiary-fixed: '#281800'
  on-tertiary-fixed-variant: '#614000'
  background: '#121318'
  on-background: '#e3e1e9'
  surface-variant: '#34343a'
typography:
  display-lg:
    fontFamily: Space Grotesk
    fontSize: 56px
    fontWeight: '700'
    lineHeight: 64px
    letterSpacing: -0.03em
  display-lg-mobile:
    fontFamily: Space Grotesk
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.02em
  headline-xl:
    fontFamily: Space Grotesk
    fontSize: 40px
    fontWeight: '600'
    lineHeight: 48px
    letterSpacing: -0.02em
  headline-xl-mobile:
    fontFamily: Space Grotesk
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.01em
  headline-lg:
    fontFamily: Space Grotesk
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: '500'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Space Grotesk
    fontSize: 20px
    fontWeight: '500'
    lineHeight: 28px
  body-lg:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Geist
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1.5rem
  gutter-sm: 1rem
  margin: 2rem
  margin-sm: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style
The design system targets users seeking an intelligent, executive-grade financial copilot. It projects precision, wealth intelligence, and calm technological mastery. The interface balances high-density monetary telemetry with atmospheric, glossy elegance.

The aesthetic blends **Dark Precision Glassmorphism** with subtle **Cybernetic Luxury**. Deep obsidian and navy-slate substrates ground the interface, while glossy, translucent glass panels introduce luminous depth. High-contrast typography guarantees financial readability, illuminated by warm mustard gold for essential actions and monetary gains, paired with electric royal purple ambient field glows indicating machine intelligence and predictive analysis.

## Colors
The palette leverages high-contrast chromatic accents over a multi-tiered obsidian base.

- **Primary (Mustard Gold - `#FACC15`, `#EAB308`, `#CA8A04`):** Represents high-value metrics, prime transactional triggers, focal status badges, and primary interactive affordances.
- **Secondary (Royal / Electric Purple - `#9333EA`, `#A855F7`, `#8B5CF6`):** Reserved for predictive AI signals, automated workflows, subtle peripheral radial blurs, and interactive hover glows.
- **Surfaces & Neutral (`#090A0F`, `#12141F`, `#181B2A`):** Foundation canvas (`#090A0F`), base card layer (`#12141F`), and elevated overlay layer (`#181B2A`).
- **Text & Contrast:** Primary text is pure crisp white (`#FFFFFF`, 100%), secondary readouts use muted slate-lavender (`#94A3B8`, 80%), and disabled states leverage deep steel (`#475569`, 50%).

Avoid flat fills on large elements; use linear vertical gradients running from 10% lighter top borders down into the obsidian surface to reinforce the glossy glass plane.

## Typography
The system employs a tri-font hierarchy to communicate technical authority and instant monetary scanning:

- **Display & Headlines (Space Grotesk):** Provides structured geometric character with subtle technical nuances, ideal for account balances, module titles, and prominent yield rates.
- **Body & Inputs (Geist):** Neutral, hyper-legible neo-grotesque engineered for complex data layouts, advisory dialogs, and conversational AI transcripts.
- **Data, Code & Indicators (JetBrains Mono):** Monospaced utility for transaction IDs, tickers, timestamps, cryptographic hashes, and percentage deltas. Keeps tabular numbers strictly aligned.

## Layout & Spacing
The layout relies on a 12-column responsive fluid grid pinned to an 8px base rhythm (`space-sm` = 8px, `space-md` = 16px, `space-lg` = 24px, `space-xl` = 40px).

- **Desktop (1200px+):** 12 columns, 24px gutters, max-width 1440px centered, 32px canvas margins.
- **Tablet (768px - 1199px):** 8 columns, 16px gutters, 24px canvas margins.
- **Mobile (<768px):** 4 columns, 16px gutters, 16px canvas margins. Multi-column financial widgets collapse into swipeable cards or single-column stacked panels.

## Elevation & Depth
Depth is produced via physical luminosity rather than standard drop shadows:

1. **Backdrop Blur & Translucency:** Panels utilize `rgba(18, 20, 31, 0.65)` layered over canvas background blurs (`backdrop-filter: blur(16px)`).
2. **Specular Glass Edge:** High-elevation containers apply an inner hairline gradient border (`1px solid rgba(255, 255, 255, 0.12)` at the top, transitioning to `rgba(255, 255, 255, 0.02)` at the base).
3. **Chromatic Backlights:** Secondary AI modules cast faint atmospheric radial gradients behind cards: `radial-gradient(circle at 50% 0%, rgba(147, 51, 234, 0.15), transparent 70%)`.
4. **Focused State Shadows:** Active interactive cards and key metrics emit a warm golden underglow: `box-shadow: 0 0 25px -5px rgba(250, 204, 21, 0.2)`.

## Shapes
The design system standardizes on modern rounded corners (`0.5rem` / 8px base radius). 

- Small actionable items (inputs, tags, chips): `rounded` (8px).
- Content cards, glass panels, and modal trays: `rounded-lg` (16px).
- Bottom sheets, floating AI assistant shells, and pill tags: `rounded-xl` (24px) or fully rounded circular ends where appropriate.

## Components

### Buttons
- **Primary:** Warm gold background (`#FACC15`) with deep obsidian text (`#090A0F`), font weight 600. On hover, transitions to bright yellow (`#FEF08A`) with an ambient gold glow (`0 0 16px rgba(250, 204, 21, 0.35)`).
- **Secondary (AI Action):** Translucent deep purple base (`rgba(147, 51, 234, 0.15)`) with an electric purple border (`rgba(168, 85, 247, 0.5)`), crisp white text, and an inner purple hover glow.
- **Ghost:** Transparent background with subtle slate border (`rgba(255, 255, 255, 0.08)`); white text transitions to `#FACC15` on hover.

### Chips & Badges
- **Status/Yield Badges:** Monospaced label (`JetBrains Mono`), rounded pill shape, `rgba(234, 179, 8, 0.12)` fill with `#FACC15` text and a hairline border.
- **AI Indicator:** Pill with a pulsating 6px electric purple dot (`#A855F7`) alongside white text.

### Input Fields
- Dark slate surface (`#12141F`) with 1px border (`rgba(255, 255, 255, 0.1)`). 
- Active focus smoothly transitions border color to `#FACC15` and engages a subtle outer glow (`0 0 0 3px rgba(250, 204, 21, 0.15)`). Placeholder text in `#64748B`.

### Cards & Panels
- Glassmorphic panels with top-down subtle linear gradient backgrounds (`rgba(24, 27, 42, 0.75)` to `rgba(18, 20, 31, 0.85)`).
- Top edge highlighted with a 1px translucent white border to simulate light hitting glass.

### Checkboxes & Radio Buttons
- Dark obsidian base with 1.5px border (`rgba(255, 255, 255, 0.2)`).
- Checked state uses solid `#FACC15` fill with obsidian checkmark glyph, accompanied by an instantaneous 8px gold blur flash upon toggle.

### Lists & Transaction Rows
- Borderless rows separated by `1px solid rgba(255, 255, 255, 0.04)`.
- Hovering reveals a sleek gradient highlight across the row (`rgba(255, 255, 255, 0.03)`), with amount text rendered in high-contrast monospaced font.