# @theme Template

## Brand Color Derivation

Derive l/c values from the `brand-lightness` input, then substitute `{brand-hue}` throughout the block.

| Lightness input | Primary l | Primary c | Secondary l | Secondary c | On-brand l |
|----------------|-----------|-----------|-------------|-------------|------------|
| `light`        | 0.65      | 0.18      | 0.55        | 0.16        | 0.15       |
| `medium`       | 0.55      | 0.18      | 0.45        | 0.16        | 0.98       |
| `dark`         | 0.40      | 0.16      | 0.32        | 0.14        | 0.98       |

## CSS Block (Tailwind v4)

Append the following block to globals.css, substituting all `{...}` variables with derived values.

```css
/* ui-brief:generated-start */
@theme {
  /* Reset: removes all default Tailwind utilities — only named tokens generate classes */
  --*: initial;

  /* Brand */
  --color-brand-primary: oklch({primary-l} {primary-c} {brand-hue});
  --color-brand-secondary: oklch({secondary-l} {secondary-c} {brand-hue});
  --color-on-brand: oklch({on-brand-l} 0.01 {brand-hue});

  /* Surface */
  --color-surface: oklch(0.98 0.005 {brand-hue});
  --color-surface-raised: oklch(0.95 0.008 {brand-hue});
  --color-surface-overlay: oklch(0.92 0.010 {brand-hue});

  /* Text */
  --color-text-primary: oklch(0.18 0.010 {brand-hue});
  --color-text-secondary: oklch(0.45 0.012 {brand-hue});
  --color-text-disabled: oklch(0.65 0.005 {brand-hue});

  /* Border */
  --color-border: oklch(0.88 0.008 {brand-hue});
  --color-border-strong: oklch(0.70 0.012 {brand-hue});

  /* Feedback */
  --color-error: oklch(0.50 0.22 25);
  --color-error-surface: oklch(0.95 0.06 25);
  --color-success: oklch(0.50 0.18 145);
  --color-success-surface: oklch(0.95 0.06 145);
  --color-warning: oklch(0.60 0.18 75);
  --color-warning-surface: oklch(0.95 0.08 75);

  /* Typography — families */
  --font-sans: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-mono: ui-monospace, "Cascadia Code", "Fira Code", "JetBrains Mono", monospace;

  /* Typography — size scale */
  --text-xs: 0.75rem;
  --text-sm: 0.875rem;
  --text-base: 1rem;
  --text-md: 1.125rem;
  --text-lg: 1.25rem;
  --text-xl: 1.5rem;
  --text-2xl: 2rem;
  --text-3xl: 2.25rem;
  --text-4xl: 3rem;

  /* Typography — weight */
  --font-weight-normal: 400;
  --font-weight-medium: 500;
  --font-weight-semibold: 600;
  --font-weight-bold: 700;

  /* Typography — leading */
  --leading-tight: 1.25;
  --leading-normal: 1.5;
  --leading-relaxed: 1.75;

  /* Spacing — 4px grid. Generates p-1=0.25rem, p-2=0.5rem … p-96=24rem automatically */
  --spacing: 0.25rem;

  /* Radius */
  --radius-none: 0;
  --radius-sm: 0.125rem;
  --radius-md: 0.375rem;
  --radius-lg: 0.5rem;
  --radius-xl: 0.75rem;
  --radius-2xl: 1rem;
  --radius-full: 9999px;

  /* Breakpoints */
  --breakpoint-sm: 640px;
  --breakpoint-md: 768px;
  --breakpoint-lg: 1024px;
  --breakpoint-xl: 1280px;
}

/* shadcn/ui CSS variable mapping — maps shadcn's expected names to semantic tokens */
:root {
  --background: var(--color-surface);
  --foreground: var(--color-text-primary);
  --primary: var(--color-brand-primary);
  --primary-foreground: var(--color-on-brand);
  --secondary: var(--color-brand-secondary);
  --secondary-foreground: var(--color-on-brand);
  --muted: var(--color-surface-raised);
  --muted-foreground: var(--color-text-secondary);
  --accent: var(--color-surface-overlay);
  --accent-foreground: var(--color-text-primary);
  --destructive: var(--color-error);
  --destructive-foreground: oklch(0.98 0.01 25);
  --border: var(--color-border);
  --input: var(--color-border);
  --ring: var(--color-brand-primary);
  --radius: var(--radius-md);
  --card: var(--color-surface-raised);
  --card-foreground: var(--color-text-primary);
  --popover: var(--color-surface-overlay);
  --popover-foreground: var(--color-text-primary);
}
@media (prefers-color-scheme: dark) {
  :root {
    --color-surface:         oklch(0.07 0.004 {brand-hue});
    --color-surface-raised:  oklch(0.11 0.005 {brand-hue});
    --color-surface-overlay: oklch(0.13 0.006 {brand-hue});
    --color-text-primary:    oklch(0.92 0.005 {brand-hue});
    --color-text-secondary:  oklch(0.50 0.006 {brand-hue});
    --color-text-disabled:   oklch(0.25 0.005 {brand-hue});
    --color-border:          oklch(0.22 0.006 {brand-hue});
    --color-border-strong:   oklch(0.38 0.008 {brand-hue});
    --color-error-surface:   oklch(0.18 0.06 25);
    --color-success-surface: oklch(0.16 0.06 145);
    --color-warning-surface: oklch(0.16 0.08 75);
  }
}
/* ui-brief:generated-end */
```

## Tailwind v3 Fallback

If `tailwind-version = v3`, skip the block above and instead append to `tailwind.config.ts`:

```
// ui-brief: semantic color tokens (Tailwind v3 — upgrade to v4 for full @theme support)
theme: {
  extend: {
    colors: {
      brand: { primary: 'oklch({primary-l} {primary-c} {brand-hue})', secondary: '...' },
      surface: { DEFAULT: 'oklch(0.98 0.005 {brand-hue})', raised: '...', overlay: '...' },
      // ... (generate full color map matching the v4 families above)
    },
    spacing: { /* 4px grid — define multipliers or use default Tailwind spacing */ },
    borderRadius: { sm: '0.125rem', md: '0.375rem', lg: '0.5rem', xl: '0.75rem', full: '9999px' },
  }
}
```
