# Image providers

Checked: **2026-09-29**. The implemented provider is OpenAI. fal is an extension boundary, not an installed adapter or an automatic fallback.

## Verified API basis

[OpenAI image generation guide](https://developers.openai.com/api/docs/guides/image-generation) documents reference-image editing, portrait output, output formats and legacy GPT Image pricing. Current guidance recommends newer 2.5 models. This skill deliberately pins the compatible **`gpt-image-1.5`** edit path; it does not claim that this is the newest model. See its [official model page](https://developers.openai.com/api/docs/models/gpt-image-1.5) and the [Images API reference](https://developers.openai.com/api/reference/resources/images).

Use the official Python SDK's `client.images.edit` with real product image input, not text-only generation. The chosen profile uses 1024 × 1536 API output, medium output quality, PNG response and high input fidelity. Verify supported arguments against the installed SDK before releasing an adapter change. High fidelity improves retention; it does not guarantee product identity.

## Reference and review contract

The edit input must include the current control composition and real product reference; references cannot be competitor products. Prompt precisely one controlled change and preserve all other visible characteristics. Keep color, shape, logo, texture, components, quantity and packaging truth intact. A generated product that differs from the reference fails review even if attractive.

Convert the output to the selected marketplace working profile without stretching or product-clipping crops. API portrait ratio differs from 3:4: use non-destructive contain/padding and review the final composition. Apply the same output treatment to all experiment images, including the control, or it becomes another variable. sRGB conversion must respect an existing ICC profile, not merely relabel pixels.

Before testing, compare each candidate to the original at full resolution and in the 180 px preview. Reject altered products, unreadable/generated pseudo-text, extra accessories or misleading claims. Preserve the original control. Do not auto-publish or announce that product preservation is guaranteed.

## Cost and authorization

No flag means dry-run: print prompts, chosen settings and the cost estimate without importing/initializing a paid client or sending a request. `--dry-run` is explicit equivalent behavior; real requests require `--run` and the seller's authorization for that generation batch.

The official guide's legacy table lists **approximately USD 0.05 output-only** for one GPT Image 1.5 medium-quality portrait, excluding input text and images. This is not the total edit price, a guaranteed quote, or a spending cap. [Current pricing](https://developers.openai.com/api/docs/pricing) and the guide's calculator must be rechecked for the actual model/account before paid use.

Record an estimate for the **entire batch**, including every candidate's repeated input images and prompt, output quality/size and applicable account pricing. The CLI requires `--estimated-cost-usd`, `--budget-usd`, `--cost-source` and `--cost-checked-on` for a paid run; the estimate must not exceed the budget. Explain that this local estimate check cannot cap provider billing. Configure any hard spending limit in the provider account separately. Never describe an output-only subtotal as the complete estimate. This adapter stores the estimate, not actual billing: reconcile actual charges in the provider account; unknown cost is not zero. Do not log keys, raw API responses or image base64.

## Failure and extension behavior

Read credentials from the environment only for an authorized paid run. Fix the endpoint to the intended provider; do not forward credentials to arbitrary base URLs. Do not automatically retry paid edits after timeouts or ambiguous failures: the request may already have been billed. Keep completed candidates and stop on failure; a new attempt needs an explicitly approved batch/estimate. Report authentication, quota, moderation and provider failures in Russian without leaking request payloads or secrets.

The provider abstraction exposes reference editing and returns image bytes; billing metadata is not currently persisted. An unsupported provider must fail visibly, not silently switch models. A future fal adapter needs separately verified model-specific reference semantics, preservation limits, dimensions, pricing and credentials. No fal dependency or paid test is part of this implementation.
