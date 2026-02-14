# The Watchman
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)
![version](https://img.shields.io/github/v/release/dummylabs/thewatchman)
[![Community Forum][forum-shield]][forum]

Home Assistant setups evolve over time—entities can disappear, and services/actions may be renamed by integrations. Watchman helps you spot these changes early by scanning your configuration for references to missing or renamed entities, so you can fix issues before automations break.

[Discussion on Home Assistant Community Forum](https://community.home-assistant.io/t/watchman-keeps-track-of-missing-entities-and-services-in-your-config-files/390391)

## Quick start
1. Go to the "Integrations" section on HACS, click "Explore and download repositories" and search for "watchman", then click "Download this repository with HACS".
2. Restart Home Assistant, go to Settings->Devices & Services->Add Integration and select Watchman integration. If integration not found, try to empty your browser cache and reload page.
3. Go to Developer Tools -> Actions, type `watchman` and select `Watchman: report` action then press "Perform Action" button. Check `watchman_report.txt` file in your configuration directory.

Refer to the [Configuration section](https://github.com/dummylabs/thewatchman#configuration) for further fine-tuning.

## What does it do
Watchman is a custom integration for Home Assistant that scans your YAML configuration files and collects referenced entities (sensors, timers, input_select, etc.) and services/actions. It then checks each entity’s current state and reports those that are missing or unavailable. For services/actions, it verifies that they exist in Home Assistant’s registry. The result can be saved as a nicely formatted text table or sent via your preferred notification method (unless the notification target itself is missing 😄). See an [example of a report](https://github.com/dummylabs/thewatchman#example-of-a-watchman-report) below.

Watchman intentionally keeps the parsing logic lightweight. It doesn’t build a full model of your configuration or try to understand dependencies between files, automations, and templates. Instead, it reads YAML files line by line and uses regex-based heuristics to detect entity and service/action references. Because of this, it may produce false positives (something looks like a reference, but isn’t) and false negatives (a real reference isn’t detected). You can silence false positives using Ignored entities and actions (see the Configuration section). Reducing false negatives is an ongoing improvement area.

## What is does not do
Watchman does not try to discover every missing or unavailable entity in your Home Assistant instance. It only reports entities and services/actions that it can find referenced in your YAML configuration (automations, scripts, dashboards, templates, etc.) and limited set of JSON files in the `config/.storage` folder, e.g. UI dashboard configurations.

## Configuration Options

[![Open your Home Assistant instance and show your integrations.](https://my.home-assistant.io/badges/integrations.svg)](https://my.home-assistant.io/redirect/integrations/)

Option | Description | Example
------------ | ------------- | -------------
⚙️ Folders to watch | Comma-separated list of folders to scan for entities and actions recursively. | `/config`
⚙️ Ignored entities and actions | Comma-separated list of items to ignore. The entity/action will be excluded from the report if their name matches a rule from the ignore list. Wildcards are supported, see [example](https://github.com/dummylabs/thewatchman?tab=readme-ov-file#ignored-entities-and-actions-formely-known-as-services-option-example) below. | `sensor.my_sensor1, sensor.my_sensor2`
⚙️ Ignored labels  | Any entity with these labels will be be excluded from the report. You can update the list of ignored labels via automation using the `watchman.set_ignored_labels` action.  | `ignore_watchman`
⚙️ Exclude entity states | Select which states will be excluded from the report | Checkboxes in UI
⚙️ Ignored files | Comma-separated list of files and folders to ignore. Wildcards are supported, see [example](https://github.com/dummylabs/thewatchman#ignored-files-option-example) below. Takes precedence over *Included folders* option.| `*/blueprints/*, */custom_components/*, */esphome/*`
⚙️ Startup delay | By default, watchman's sensors are updated by `homeassistant_started` event. Some integrations may require extra time for intiialization so that their entities/actions may not yet be ready during watchman check. This is especially true for single-board computers like Raspberry PI. This option allows to postpone startup sensors update for certain amount of seconds. | `0`
⚙️ Exclude entities used by disabled automations | If enabled, entities referenced only by disabled automations will be excluded from the report. | UI flag
⚙️ Obfuscate sensitive data in logs | By default, potentially sensitive data, such as entity IDs, are masked in debug logs. This option enables the display of full entity names and actions in log files. | UI flag 
⚙️ Report location | Report location and filename. | `/config/watchman_report.txt`
⚙️ Custom header for the report | Custom header for watchman report. | `-== Watchman Report ==-`
⚙️ Report's column width | Report's columns width. The list of column widths for the table version of the report. | `30, 7, 60`
⚙️ Add friendly names | Add friendly name of the entity to the report whenever possible. | UI flag


### Ignored files option example
* Ignore a file: `*/automations.yaml`
* Ignore all files in the folder: `/config/esphome/*`
* Ignore several folders: `/config/custom_components/*, /config/appdaemon/*, /config/www/*`
<img src="https://raw.githubusercontent.com/dummylabs/thewatchman/main/images/ignored_files_ui.png" width=50%>

### Ignored entities and actions example
* Ignore an entity: `person.dummylabs`
* Ignore everything in sensor domain: `sensor.*`
* Ignore any entity/action which name ends with "_ble": `*.*_ble`

## Report Action Parameters
The text version of the report can be generated using `watchman.report` action from Developer Tools UI, an automation or a script. Default location is `/config/thewatchman_report.txt`, which can be changed in the UI configuration. A long report can be split into several messages (chunks) due to limitations imposed by some notification actions (e.g., telegram). Action behaviour can be altered with additional optional parameters:

Parameter | YAML key | Description | Default
------------ | ------------- | -------------| -------------
⚙️ Force configuration parsing |`parse_config`| Forces watchman to parse Home Assistant configuration files and rebuild entity and actions list. Usually this is not required as watchman will automatically parse files once Home Assistant restarts or tries to reload its configuration. | `False`
⚙️ Send report as notification |`action`| Home assistant notification action to send report via, e.g. `persistent_notification.create`. See compatibility note below.| ``
⚙️ Notification action data |`data`| A json object with additional notification action parameters. See [example](https://github.com/dummylabs/thewatchman#send-report-via-telegram-bot) below.  | `None`
⚙️ Message chunk size |`chunk_size`| Maximum message size in bytes. Some notification actions, e.g., Telegram, refuse to deliver a message if its size is greater than some internal limit. If report text size exceeds `chunk_size`, the report will be sent in several subsequent notifications. `0` value will disable chunking. | `3500`


### A (useless) example sending report as persitent notification
```yaml
action: watchman.report
data:
  parse_config: true
  action: persistent_notification.create
  data:
    title: Watchman Report
  chunk_size: 3500
  create_file: true`
```

## Sensors

> [!NOTE]
> Versions prior to 0.6.4 had a sensor named `sensor.watchman_missing_services`. Latest versions use another name: `sensor.watchman_missing_actions` if integration was installed from scratch (new user).
> Existing users who upgraded from previous versions will have old sensor name to preserve compatibilty with their scripts and dashboards. They can rename sensor themselves or just remove integration and install it again.

Besides of the report, integration provides a few diagnostic sensors which can be used within automations or dashboards:
Sensor                             | Meaning
---------------------------------- | -------------
`sensor.watchman_status`           | See "Status meanings" below.
`sensor.watchman_last_parse`       | Date and time of last parse. Usually it only occurs during HA restart or when HA configuration is reloaded.
`sensor.watchman_missing_entities` | Number of flagged entities in the report.
`sensor.watchman_missing_actions`  | Number of flagged actions in the report.
`sensor.watchman_last_updated`     | Date and time of the last update for the sensors above. Watchman sensors update whenever a configured entity changes status (e.g., becomes unavailable, goes missing, or returns to a functional state).
`sensor.watchman_parse_duration`   | Time taken for the last parse attempt. This value helps monitor system performance to ensure that Watchman operates efficiently without over-consuming system resources.
`sensor.watchman_processed_files`  | The number of configuration files processed by Wathcman. 
`sensor.watchman_ignored_files`    | The number of ignored configuration files.

## Status Meanings
The status indicates what Watchman is currently doing:

- **Idle**: Doing nothing; everything is working fine.
- **Waiting for HA**: Occurs after a reboot. Watchman waits for HA to fully load before starting monitoring.
- **Parsing**: Watchman is parsing your configuration. The first run may take some time, but subsequent runs use cached results and should take only fractions of a second.
- **Pending**: Parser will start parsing soon.
- **Safe Mode**: Watchman detected that Home Assistant restarted during an unfinished parse, which might indicate a freezing problem. It will not process events, sensors, or files.
Tip: Safe Mode can be disabled by deleting the watchman.lock (or watchman_dev.lock) file in the .storage folder, or simply by reinstalling the integration.


## Example of a watchman report
Please note that the ASCII table format is only used when report is saved to a file. For notification actions watchman uses plain text list due to presentation limitations.
### Icons meaning:
* 👥 - A group in UI Helpers which contains flagged entity
* 🧩 - A template entity in UI Helpers which contains flagged entity
* 📄 - Regular configuration file which contains flagged entity

```
-== WATCHMAN REPORT ==-

-== Missing 3 entity(ies) from 114 found in your config:
+--------------------------------+----------+----------------------------------------+
| Entity ID                      | State    | Location                               |
+--------------------------------+----------+----------------------------------------+
| binary_sensor.oops             | unknown  | 👥 Group: "A helper created in the UI" |
| sensor.does_not_exist          | missing  | 🧩 Template: "Another helper "         |
| binary_sensor.tasks_payments   | unavail  | 📄 .storage/lovelace:95                |
|                                |          | 📄 automations.yaml:271                |
+--------------------------------+----------+----------------------------------------+

-== Report created on 03 Feb 2022 17:18:55
-== Parsed 200 files in 0.96s., ignored 66 files
-== Generated in: 0.01s. Validated in: 0.00s.
```
The legend at the bottom of the report shows time consumed by 3 coherent stages: parse configuration files, validate each entity/action state and generate text version of the report.

## Youtube Reviews
### Everything Smart Home channel
[![Watch the video](https://img.youtube.com/vi/XKD5vBZLKgE/0.jpg)](https://www.youtube.com/watch?v=XKD5vBZLKgE)

### mostlychris channel
[![Watch the video](https://img.youtube.com/vi/E489fTZHywI/0.jpg)](https://www.youtube.com/watch?v=E489fTZHywI)

### Smart Home Australia channel
[![Watch the video](https://img.youtube.com/vi/J41HYbtBsbQ/0.jpg)](https://www.youtube.com/watch?v=J41HYbtBsbQ)

### Smart Home Makers channel
[![Watch the video](https://img.youtube.com/vi/iHQYs-YA2uo/0.jpg)](https://www.youtube.com/watch?v=iHQYs-YA2uo)

### Sascha Brockel channel
[![Watch the video](https://img.youtube.com/vi/qYHMoTlheuA/0.jpg)](https://www.youtube.com/watch?v=qYHMoTlheuA)

[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=popout
[forum]: https://community.home-assistant.io/t/watchman-keeps-track-of-missing-entities-and-services-in-your-config-files/390391
