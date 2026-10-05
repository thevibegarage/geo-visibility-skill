# JSON-LD templates

Paste into the page `<head>` or just before `</body>` in the server-rendered HTML. Replace every `{{PLACEHOLDER}}` with real, visible-on-page facts. Remove properties you cannot support. Validate with Google's Rich Results Test and validator.schema.org.

## Organization (homepage / about)
```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "@id": "{{SITE_URL}}/#organization",
  "name": "{{BRAND_NAME}}",
  "legalName": "{{LEGAL_NAME}}",
  "url": "{{SITE_URL}}",
  "logo": "{{LOGO_URL}}",
  "description": "{{ONE_SENTENCE_DEFINITION}}",
  "foundingDate": "{{YYYY}}",
  "founder": [{ "@type": "Person", "name": "{{FOUNDER_NAME}}", "sameAs": "{{FOUNDER_LINKEDIN}}" }],
  "address": { "@type": "PostalAddress", "addressLocality": "{{CITY}}", "addressCountry": "{{COUNTRY}}" },
  "contactPoint": [{ "@type": "ContactPoint", "contactType": "customer support", "email": "{{EMAIL}}" }],
  "sameAs": ["{{LINKEDIN_URL}}", "{{X_URL}}", "{{YOUTUBE_URL}}", "{{GITHUB_URL}}", "{{CRUNCHBASE_URL}}", "{{G2_URL}}"]
}
</script>
```

## WebSite
```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "WebSite",
  "@id": "{{SITE_URL}}/#website",
  "url": "{{SITE_URL}}",
  "name": "{{BRAND_NAME}}",
  "publisher": { "@id": "{{SITE_URL}}/#organization" }
}
</script>
```

## Article / blog post
```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "{{TITLE}}",
  "description": "{{DIRECT_ANSWER_SUMMARY}}",
  "author": { "@type": "Person", "name": "{{AUTHOR}}", "url": "{{AUTHOR_PAGE}}", "sameAs": "{{AUTHOR_LINKEDIN}}" },
  "publisher": { "@id": "{{SITE_URL}}/#organization" },
  "datePublished": "{{YYYY-MM-DD}}",
  "dateModified": "{{YYYY-MM-DD}}",
  "mainEntityOfPage": "{{PAGE_URL}}",
  "image": "{{IMAGE_URL}}"
}
</script>
```

## FAQPage (content must match visible FAQ text)
```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "{{QUESTION}}",
      "acceptedAnswer": { "@type": "Answer", "text": "{{CONCISE_ANSWER}}" }
    }
  ]
}
</script>
```

## SoftwareApplication (SaaS)
```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "{{PRODUCT_NAME}}",
  "applicationCategory": "{{e.g. BusinessApplication}}",
  "operatingSystem": "Web",
  "description": "{{DESCRIPTION}}",
  "offers": { "@type": "Offer", "price": "{{PRICE}}", "priceCurrency": "{{CUR}}", "url": "{{PRICING_URL}}" },
  "publisher": { "@id": "{{SITE_URL}}/#organization" }
}
</script>
```
Add `aggregateRating` only if the ratings are real and visible on the page.

## Product (physical goods)
```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "{{NAME}}",
  "description": "{{DESCRIPTION}}",
  "sku": "{{SKU}}",
  "brand": { "@type": "Brand", "name": "{{BRAND_NAME}}" },
  "offers": { "@type": "Offer", "price": "{{PRICE}}", "priceCurrency": "{{CUR}}", "availability": "https://schema.org/InStock", "url": "{{PRODUCT_URL}}" }
}
</script>
```

## LocalBusiness
```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "LocalBusiness",
  "name": "{{BRAND_NAME}}",
  "url": "{{SITE_URL}}",
  "telephone": "{{PHONE}}",
  "address": { "@type": "PostalAddress", "streetAddress": "{{STREET}}", "addressLocality": "{{CITY}}", "postalCode": "{{ZIP}}", "addressCountry": "{{COUNTRY}}" },
  "openingHours": "{{e.g. Mo-Fr 09:00-18:00}}",
  "sameAs": ["{{GOOGLE_BUSINESS_PROFILE_URL}}"]
}
</script>
```

## BreadcrumbList
```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [
    { "@type": "ListItem", "position": 1, "name": "Home", "item": "{{SITE_URL}}" },
    { "@type": "ListItem", "position": 2, "name": "{{SECTION}}", "item": "{{SECTION_URL}}" }
  ]
}
</script>
```
