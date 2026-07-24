# Waste Management New Zealand PayAsUGO for Home Assistant

[![GitHub Release](https://img.shields.io/github/v/release/reticentnz/ha-wm-nz-payasugo?include_prereleases)](https://github.com/reticentnz/ha-wm-nz-payasugo/releases)

An experimental Home Assistant custom integration for Waste Management New
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

Copy `custom_components/payasugo` into the `custom_components` directory in
your Home Assistant configuration, restart Home Assistant, then add
**Waste Management New Zealand PayAsUGO** from
**Settings → Devices & services**.

For HACS, add this repository as a custom integration repository and install
it, then restart Home Assistant.

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

## Development status

The request and response models are based on a browser capture from July 2026.
The integration should be treated as experimental until its login bootstrap
and collection workflow have been tested against a Home Assistant instance.
