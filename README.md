# Waste Management New Zealand PayAsUGO for Home Assistant

[![GitHub Release](https://img.shields.io/github/v/release/reticentnz/ha-wm-nz-payasugo?include_prereleases)](https://github.com/reticentnz/ha-wm-nz-payasugo/releases)
[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/reticentnz/ha-wm-nz-payasugo/actions/workflows/validate.yml/badge.svg)](https://github.com/reticentnz/ha-wm-nz-payasugo/actions/workflows/validate.yml)

An unofficial Home Assistant custom integration for Waste Management New
Zealand's PayAsUGO collection service.

This project is specifically for the New Zealand service at
`payasugo.wastemanagement.co.nz`. It is not for, or affiliated with, the
similarly named Waste Management company in the United States.

It provides:

- A timestamp sensor for the next collection.
- A switch that pauses or re-enables the next collection.
- Collection status and product family as sensor attributes.

> [!WARNING]
> PayAsUGO does not publish a supported public API. This integration uses the
> private Salesforce Aura interface used by the PayAsUGO website and may need
> updates when that website changes.

## Installation

### HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=reticentnz&repository=ha-wm-nz-payasugo&category=integration)

1. Open HACS in Home Assistant.
2. Search for and install **Waste Management New Zealand PayAsUGO**.
3. Restart Home Assistant.
4. Add the integration from **Settings → Devices & services**.

### Manual

Copy `custom_components/payasugo` into the `custom_components` directory in
your Home Assistant configuration, restart Home Assistant, then add the
integration from **Settings → Devices & services**.

## Configuration

Setup requires:

- Your PayAsUGO email and password.

After sign-in, the integration retrieves the active service addresses attached
to the account and presents them in a dropdown. Add each address as a separate
integration entry if you want to manage multiple properties.

Credentials are stored in Home Assistant's config entry storage. They are sent
only to `payasugo.wastemanagement.co.nz`.

The switch is disabled after the documented pause cutoff, 7:00 AM two days
before the collection date.

Collection information is refreshed every 24 hours, when the integration is
loaded, and immediately after a collection is paused or re-enabled. A failed
scheduled refresh is retried after 5, 15, 30, and then 60 minutes rather than
leaving the entities unavailable until the next daily refresh.

## Reliability and compatibility

The request and response models are based on a browser capture from July 2026.
The integration has been running reliably on a Home Assistant instance,
including setup and the collection workflow. Because it relies on the
unsupported private API used by the PayAsUGO website, website changes may still
require integration updates.

## Support

Report defects through the
[GitHub issue tracker](https://github.com/reticentnz/ha-wm-nz-payasugo/issues).
When reporting a problem, download the integration's diagnostics from
**Settings → Devices & services → PayAsUGO → three-dot menu → Download
diagnostics** and attach that file to the issue. The diagnostics use a strict
allowlist and exclude passwords, email addresses, street addresses, cookies,
tokens, account and collection IDs, and other identifiers.

Do not create or attach HAR files. They contain authenticated private API
traffic and may expose credentials and customer information that the safe
diagnostics intentionally omit.

## Disclaimer

This is an unofficial community project. It is not endorsed by or affiliated
with Waste Management New Zealand. PayAsUGO does not publish a supported API,
so website changes may require integration updates.
