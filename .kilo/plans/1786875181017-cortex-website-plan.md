# Cortex Website Plan

## Company Overview

**Company Name:** Cortex
**Slogan:** Intelligent sandboxed testing for modern development teams

Cortex is a software company that provides sandboxed testing and execution platforms for development teams. Our platform enables teams to run tests in isolated containers, verify claims with cryptographic receipts, and integrate testing into their CI/CD pipelines with confidence.

## Products

### 1. workflo
**The sandboxed execution engine**

workflo is our flagship product that runs code in isolated Docker sandboxes with comprehensive test execution capabilities.

**Key Features:**
- Execute pytest test suites in secure containers
- Playwright browser probes for web application testing
- Three test tiers: surface (--test), deep (--deep-test), aggressive (--aggressive-test)
- Security mode with tenant isolation and network canary checks
- Ed25519 signed receipts for claim verification (Claim #4)
- Configurable resource limits (CPU, memory, timeout)
- Multiple worker images: surface, deep, and web-enabled variants
- REST API contract integration via control plane

**CLI Usage:**
```
workflo run --repo <url> --test --security
workflo run --repo <url> --deep-test
workflo run --repo <url> --web --start-command "python app.py" --port 5000
workflo verify --receipt report.json --pubkey pubkey.pem
workflo keygen --output pubkey.pem --force
```

**Target Audience:** Dev teams, QA engineers, security teams who need to run tests in isolated environments with verified results.

---

### 2. cortex Nexus
**(To be explained by user later)**

*Pending detailed product specification. Expected to provide additional capabilities in the cortex portfolio.*

---

### 3. cortex ASTRA
**(To be explained by user later)**

*Pending detailed product specification. Expected to provide additional capabilities in the cortex portfolio.*

---

## Website Structure

### Pages

1. **Homepage (`/`)**
   - Hero section with headline and subheadline
   - Key product highlights grid (workflo, cortex Nexus, cortex ASTRA)
   - Trust badges / logos
   - Call-to-action buttons (Get Started, Docs, Pricing)

2. **Products (`/products`)**
   - Overview of all three products
   - Dedicated sections for workflo, cortex Nexus, cortex ASTRA
   - Feature comparison table
   - Deep-dive links to product detail pages

3. **workflo Details (`/products/workflo`)**
   - Feature list specific to workflo
   - CLI reference overview
   - Supported probe groups (surface, deep, aggressive, security, web)
   - Worker image options
   - Getting started guide

4. **cortex Nexus (`/products/nexus`)**
   - Placeholder/product detail section

5. **cortex ASTRA (`/products/astra`)**
   - Placeholder/product detail section

6. **About (`/about`)**
   - Company mission and values
   - Team information
   - Blog/posts (if applicable)

7. **Docs (`/docs`)**
   - Getting started guides
   - CLI reference
   - API documentation
   - Architecture diagrams
   - Integration guides

8. **Contact (`/contact`)**
   - Contact form
   - Email address
   - Twitter/LinkedIn links
   - Discord/Community links

### Additional Pages (if applicable)

- **Pricing (`/pricing`)** - Tiered pricing plans
- **Changelog (`/changelog`)** - Recent updates
- **Security (`/security`)** - Security commitments and certifications

### Homepage Hero Section Example

```
# Intelligent sandboxed testing for modern development teams

Run pytest, Playwright, and custom tests in isolated Docker containers with cryptographic receipt verification.

[Get Started with workflo]  [View Docs]

*Trusted by engineering teams at startups and enterprises*
```

### Products Grid (Homepage)

| Product | Description | CTA |
|---------|-------------|-----|
| **workflo** | Sandboxed test execution engine with pytest and Playwright support | Try for Free |
| **cortex Nexus** | Next-gen testing capabilities | Learn More |
| **cortex ASTRA** | Advanced testing intelligence | Learn More |

### workflo Feature Highlights Section

- **Isolated Execution**: Run tests in secure Docker containers with resource limits
- **Multiple Probe Groups**: surface (basic pytest), deep (LLM-generated edge cases), aggressive (fuzz/chaos), security (tenant isolation), web (Playwright browser probes)
- **Cryptographic Receipts**: Every run produces a signed receipt verified via Ed25519 public keys (Claim #4)
- **Flexible Worker Images**: Choose from surface, deep, and web-optimized worker images
- **REST API Integration**: Round-trip through control plane for enterprise deployments
- **CLI & API**: Choose between local CLI workflow or remote API integration

### Getting Started Section

Three-step onboarding:

1. **Connect** - Link your repository or control plane instance
2. **Configure** - Select probe groups, resource limits, and worker images
3. **Execute** - Run `workflo run` locally or via API, verify signed receipts

### Technical Integrations

- **Control Plane API**: POST /v1/runs, GET /v1/runs/{id}
- **CLI Integration**: `workflo run --via-api <url>`
- **CI/CD Integration**: GitHub Actions, GitLab CI templates
- **Dashboard**: Next.js dashboard for run history and SOC 2 evidence

### Footer Links

- Docs
- Blog
- GitHub Repository
- Support
- Privacy Policy
- Terms of Service

## Design Guidelines

- **Color Palette**: Professional dark/light theme with accent colors distinguishing each product
- **Typography**: Clean, readable sans-serif fonts
- **Imagery**: Docker/container illustrations, code snippets, test result visualizations
- **Responsive**: Mobile-first design, works on all device sizes
- **Accessibility**: WCAG AA compliance, keyboard navigation, screen reader friendly

## Technical Stack Recommendations

- **Framework**: Next.js 14 with App Router
- **UI Components**: Tailwind CSS, shadcn/ui or custom component library
- **Authentication**: OAuth + API key management (matching workflo CLI flow)
- **Deployment**: Vercel or self-hosted Docker container
- **Analytics**: Plausible or simple page tracking
- **Icons**: Lucide React or similar icon set

## Open Questions (to be resolved with user)

1. Detailed feature set for cortex Nexus product
2. Detailed feature set for cortex ASTRA product
3. Pricing strategy and tier structure
4. Color scheme and branding preferences
5. Whether to integrate directly with the existing workflo codebase or keep as separate marketing site
6. Target audience and primary use cases
7. Required integrations (DataHub, control plane, CI/CD platforms)

## Validation Checklist

- [ ] Homepage hero conveys value proposition clearly
- [ ] All three products have dedicated sections
- [ ] workflo section includes key features from the existing codebase
- [ ] Navigation works across all pages
- [ ] Mobile responsive design verified
- [ ] Contact form functional (or placeholder)
- [ ] Docs section has getting started content
- [ ] Color scheme matches corporate branding
- [ ] All CTA buttons prominent and functional