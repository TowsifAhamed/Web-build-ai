Business name: Pookies & Pirates — playful children’s-wear store
Proposed tagline: "Playful style for little adventurers."

Structure & key pages

Home –
- Hero banner (headline, sub-line, CTA).
- 4-tile category grid (Newborn, Boys, Girls, Mom Picks).
- "Shop the Look" scroll-snap carousel.
- Instagram / UGC feed (#PookiesNPiratesKids).
- Value-props row (100 % cotton · Easy returns · Made in BD).
- Newsletter call-out, then full footer.

Shop (Product-listing) – Infinite-scroll grid (2 × mobile, 3–4 × desktop) with size, price, color & theme filters.

Product detail – 4-image gallery with click-zoom, size guide modal, stock badge, cross-sell strip ("Pair with"). Sticky add-to-cart on scroll.

About – Story timeline, founders’ photos, ethical sourcing pledge.

Blog / Tips – Parenting and styling mini-articles (SEO).

Contact / FAQ – Accordion FAQ, contact form, WhatsApp chat link.

Cart & single-page checkout – Steps: shipping → payment → review. Integrate bKash, Nagad, Stripe, COD.

Responsive grid
- Breakpoints: 640 / 768 / 1024 / 1280 px.
- Container widths: 95 %, 90 %, max 1140 px.
- CSS Grid & Flexbox; semantic HTML5.

Design style:
Overall vibe: Modern store-front clarity with cheerful, story-book flourishes. Clean lines, lots of white space, rounded cards, and gentle drop-shadows keep things light and kid-friendly.

Personality: Friendly, imaginative, trustworthy. Nautical hints (dotted treasure-map paths, compass icons) reinforce the "pirates" theme without clutter.

Typography:
- Headings: Poppins Semibold — rounded, welcoming.
- Body copy: Inter (system-ui fallback) for easy reading.
- Responsive type scale (e.g., h1 ≈ clamp 2.4–3.2 rem).

Imagery: Bright lifestyle photos of laughing kids, outdoor garden scenes, flat-lay product shots on pastel surfaces.

UI details: Large pill buttons, hover "lift" animation on cards, ripple effect on primary CTAs, sticky nav that shrinks on scroll, bottom sticky bar on mobile (Home, Shop, Cart, Profile).

Color scheme:
Primary (teal) #005F73 – Brand anchor / links / buttons
Secondary (gold) #FFC300 – Highlights, sale badges
Accent 1 (pink) #EF476F – Add-to-cart, error states
Accent 2 (mint) #06D6A0 – Success, discounts
Background #FFFFFF – Main page canvas
Surface cards #F4F7FA – Product tiles, modals
Text / headings #1F2937 – High-contrast copy

Follow the 60-30-10 rule: 60 % neutrals, 30 % primary teal, 10 % accents.

Additional instructions: Code guidelines
- Pure HTML5 & CSS3 (no Bootstrap/Tailwind).
- BEM naming + CSS custom properties for colors/spacing.
- Core CSS ≤ 40 KB gzipped; bundle future JS ≤ 150 KB gzipped.
- Add data-* hooks to interactive elements for later JS.

Accessibility – WCAG 2.2 AA: logical heading order, alt text, focus rings (2 px dashed #EF476F), contrast ≥ 4.5 : 1.

Performance targets – LCP < 2.5 s, CLS < 0.1, total blocking time < 150 ms. Use WebP images, font-display:swap, preload hero image.

SEO – Descriptive <title> and meta description; canonical URLs; JSON-LD for Product & Organization.

Analytics & marketing – GA4, Meta Pixel; Klaviyo events for browse abandon. Exit-intent coupon pop-up.

DevOps – GitHub repo with Vercel / Netlify CI-CD; staging branch previews; nightly DB dump.

Tone & microcopy – Friendly Banglish phrases (e.g., empty cart: “Ektu wait, captain — your loot is empty!”).

Uploaded images: logo.jpg, cover.jpeg
