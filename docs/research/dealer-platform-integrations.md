# Dealer inventory integration research

Checked 15 November 2026. These are public documentation findings, not confirmation of this dealership's account capabilities. No authenticated dealer dashboard or dealer-specific export was inspected.

## This dealership: SellMyCar

- Confirmed by the user: the source PC runs Windows.
- User-supplied QatarSale profile: [SellMyCar Showroom](https://qatarsale.com/en/showroom/sell_my_car_showroom). A read-only public-page snapshot retrieved on 15 November 2026 displayed **108** beside `marketList` and pagination for three pages. The selected view was **All**, with Bikes and Cars For Sale categories available. Therefore 108 is the displayed aggregate result count, **not a verified count of live cars**. Only the first page was inspected; no crawl or full inventory import was performed.
- User-supplied Qatar Living profile: [SellMyCar showroom](https://www.qatarliving.com/en/vehicles/showrooms/sellmycar-1326). Recorded as the intended account URL. This specific profile has not been retrieved or crawled in this research, so its count and inventory contents are unverified. The terms below require written consent for automated collection.
- Initial reconciliation should request the dealership's own account exports and current-stock confirmation, and should retain these exact source identities. Do not add the two sites' displayed counts: the same car can appear on both.

## Qatar Living

- Its official terms require **prior express written consent** for automated scraping, crawling, monitoring, indexing and collection. They direct consent requests to `support@qatarliving.com`. Automated posting through its web interface also requires consent. Short source excerpts: “prior express written consent”; “without our consent”. An account holder's ownership of their adverts does not establish platform consent for automated access. [Official Terms of Use](https://www.qatarliving.com/en/page/terms-of-use)
- Public showroom pages can expose a dealership's offered cars, listing count and pagination. For example, the Q-auto page showed a Cars for Sale count and two pages. This verifies a possible reconciliation input, not an authoritative physical stock or sales register. [Example showroom page](https://www.qatarliving.com/en/vehicles/showrooms/q-auto-1334)
- The official vehicles site advertises verified dealers, showrooms and subscriptions. Public searches did **not** locate official developer documentation for a posting/feed API, inventory export, webhooks or a comprehensive sold archive. Their existence and dealer access remain unverified; ask the account manager for supported integration and historic export options. [Vehicles site](https://www.qatarliving.com/en/vehicles), [showroom directory](https://www.qatarliving.com/en/vehicles/showrooms)

## QatarSale

- A public showroom directory and showroom inventory pages exist. An example showroom page exposed a count and vehicle entries. Counts must be interpreted with category filters and pagination. [Official showroom directory](https://www.qatarsale.com/en/showroom-list/cars_for_sale), [example inventory](https://qatarsale.com/en/showroom/deals_on_wheels)
- Public model results include **Sold** labels, dates and asking prices. This confirms some historical advertisements remain accessible, not that every sold advert or this seller's full history is available. Displayed asking prices are not verified transaction prices. [Example model results](https://qatarsale.com/en/products/cars_for_sale/geely-okavango)
- A linked historical detail page exposed structured specifications and features. The retrieved detail snapshot said For Sale while the result snapshot labelled it Sold; fetch metadata showed different crawl dates. This is evidence that cached observations can disagree, not proof of a current platform bug. Preserve observation time and source; reconcile conflicts. [Example detail page](https://qatarsale.com/en/product/geely_okavango_2022_white_automatic_suv-634106)
- The accessible English terms cover general use and auctions and say Arabic prevails in a language conflict. They do not establish a public API or permission to crawl. No official public feed/posting API documentation was located in targeted public searches. Private dealer integrations and additional account terms remain unverified. [Official conditions](https://qatarsale.com/en/TermsOfService)

## Recommended integration boundary

These are engineering recommendations derived from the findings above:

1. Keep the dealership's reviewed database as the stock authority. Keep each platform's listing state separately: live, sold-labelled, expired, removed, unknown. A missing listing never automatically means the vehicle sold.
2. Initially import account exports or owner-supplied listing details and prepare copyable publishing packages. Enable platform automation only through a confirmed supported feed/API or explicit permission. Qatar Living crawling and automated web posting need platform consent.
3. Ask both platforms about create/update/unpublish support, stable listing identifiers, inventory exports, sold/expired archives, pagination, rate limits, authentication and dealer packages. Do not build against guessed private endpoints.
4. Match by verified VIN or stock number first, stable external IDs next. Treat make/model/year, price and similar photos as candidate evidence requiring review; several vehicles can share them.
5. Record source URL or export identity, external listing ID, seller identity, observed state, observed time, imported content and matching confidence. Treat only this dealership's verified descriptions as content candidates. Generate new drafts from confirmed facts and retain approval before publication.
6. Use a publication queue with per-platform results and retries. A new inventory record creates a review task, not an immediate public advert. A reviewed sale should queue removals/updates on every active channel, with pending and failed work visible.

## Remote access from UAE to a Windows PC in Qatar

Use **Windows OpenSSH over the Tailscale private network**. Tailscale SSH is a different service: its server component currently supports Linux and the open-source macOS CLI combination, not Windows. Windows can still run Microsoft's native SSH server over Tailscale connectivity. [Tailscale SSH prerequisites](https://tailscale.com/docs/features/tailscale-ssh), [traditional SSH over Tailscale](https://tailscale.com/docs/reference/ssh-over-tailscale)

Documented setup ingredients:

- Install Tailscale on both PCs, authenticate into an appropriately restricted network and permit only the intended administrator/device to reach the target SSH port. Windows installation and supported versions are documented. [Windows installation](https://tailscale.com/docs/install/windows)
- On the Qatar PC, an administrator can install the Windows optional OpenSSH Server capability and start `sshd`, then set its startup type to Automatic. Microsoft's installation automatically creates an inbound port-22 firewall rule; narrow that rule to the intended Tailscale source rather than leaving broad inbound access. No router port forwarding is needed for the proposed private-network design. [Microsoft installation and commands](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse)
- Use a dedicated Windows account with access to the inventory directories and public-key authentication. Standard accounts use `C:\Users\<user>\.ssh\authorized_keys`; administrative accounts use `C:\ProgramData\ssh\administrators_authorized_keys` with specific ACL requirements. Keep the private key on the UAE client. [Microsoft key-management commands](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement)
- Find the target address with `tailscale ip`, then connect using `ssh <windows-user>@<tailscale-ip>` or the MagicDNS hostname. [Connection commands](https://tailscale.com/docs/reference/ssh-over-tailscale)
- For access after logout, Tailscale documents Windows unattended mode (`--unattended`). The machine still needs power, internet and attached inventory drives; unattended mode cannot wake a powered-off machine. Schedule folder scans locally so routine importing does not depend on an open remote session. [CLI flags](https://tailscale.com/docs/reference/tailscale-cli)

These steps are a proposed runbook, not changes made to either PC. Account names, drive paths, supported Windows version and remote connectivity still need to be established.

## Local registration-card OCR

- Tesseract supports multiple languages in one invocation, and its language-data list includes `eng` (English) and `ara` (Arabic). With both models installed, a local extraction command is `tesseract card.jpg stdout -l eng+ara`. This runs text recognition; it does not establish a Qatar registration-card field parser. [Official CLI usage](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html), [language models](https://tesseract-ocr.github.io/tessdoc/Data-Files-in-different-versions.html)
- Image resolution, noise, orientation, segmentation and preprocessing affect OCR accuracy. Test on actual card layouts and photos before selecting extraction rules. [Official quality guide](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html)
- Recommended handling: store extracted fields as proposals with provenance; review VIN, year, make and model; distinguish model year from registration/expiry dates. Leave absent or conflicting fields unknown. Keep card images and raw text private and exclude them from public photo uploads. Do not infer mileage, trim options, accident history or warranty from a registration card unless those facts are independently verified.
