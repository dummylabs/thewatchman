# The Watchman
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)
![version](https://img.shields.io/github/v/release/dummylabs/thewatchman)
[![Community Forum][forum-shield]][forum]


The world around us is constantly changing, and so is Home Assistant. How often have you found yourself in a situation where your automations stopped working because some entities became permanently unavailable or actions changed their names? Some integrations can easily change the name of its actions and sensors they expose to Home Assistant. The watchman is an attempt to control such unwelcome changes and enable you to react proactively before any critical automation gets broken.

[Discussion on Home Assistant Community Forum](https://community.home-assistant.io/t/watchman-keeps-track-of-missing-entities-and-services-in-your-config-files/390391)

## Quick start

1. Go to the "Integrations" section on HACS, click "Explore and download repositories" and search for "watchman", then click "Download this repository with HACS".
2. Restart Home Assistant, go to Settings->Devices & Services->Add Integration and select Watchman integration. If integration not found, try to empty your browser cache and reload page.
3. Go to Developer Tools -> Actions, type `watchman` and select `Watchman: report` action then press "Perform Action" button. Check `watchman_report.txt` file in your configuration directory.

Refer to the [Configuration section](https://github.com/dummylabs/thewatchman#configuration) for further fine-tuning.

## What does it do
The Watchman is a custom integration for Home Assistant that collects all entities (sensors, timers, input_selects, etc.) mentioned in your YAML configuration files, as well as all actions. It checks the actual state of each entity one by one and reports those that are unavailable or missing. For actions, it verifies their availability in the Home Assistant actions registry. The report can be stored as a nicely formatted text table or sent via your chosen notification method (unless the notification method itself is missing :smile:). Check out an [example of a report](https://github.com/dummylabs/thewatchman#example-of-a-watchman-report) below.

The integration has very simple internals. It knows nothing about complex relationships and dependencies among YAML configuration files, nor about the semantics of entities and automations. It parses YAML files line by line and tries to guess references either to an entity or an action based on regular expression heuristics. This means the integration can produce both false positives (when it looks like a duck, but is not) and false negatives (when some entity in a configuration file is not detected by the integration). To ignore false positives, the **Ignored entities and actions** parameter can be used (see Configuration section below). Improvements for false negatives are a goal for future releases.

## What is does not do
The Watchman will not report every unavailable or unknown entities within your system — only those that are actively used by Home Assistant, whether it is an automations, dashboard configuration, template sensor, etc.

## Configuration Options

Integration settings are available in Settings->Devices & Services->Watchman->Configure

[![Open your Home Assistant instance and show your integrations.](https://my.home-assistant.io/badges/integrations.svg)](https://my.home-assistant.io/redirect/integrations/)

Option | Description | Example
------------ | ------------- | -------------
Folders to watch | Comma-separated list of folders to scan for entities and actions recursively. | `/config`
Ignored entities and actions | Comma-separated list of items to ignore. The entity/action will be excluded from the report if their name matches a rule from the ignore list. Wildcards are supported, see [example](https://github.com/dummylabs/thewatchman?tab=readme-ov-file#ignored-entities-and-actions-formely-known-as-services-option-example) below. | `sensor.my_sensor1, sensor.my_sensor2`
Exclude entity states | Select which states will be excluded from the report | Checkboxes in UI
Ignored files | Comma-separated list of files and folders to ignore. Wildcards are supported, see [example](https://github.com/dummylabs/thewatchman#ignored-files-option-example) below. Takes precedence over *Included folders* option.| `*/blueprints/*, */custom_components/*, */esphome/*`
Startup delay | By default, watchman's sensors are updated by `homeassistant_started` event. Some integrations may require extra time for intiialization so that their entities/actions may not yet be ready during watchman check. This is especially true for single-board computers like Raspberry PI. This option allows to postpone startup sensors update for certain amount of seconds. | `0`
Parse UI controlled dsahboards | Parse Dashboards UI (ex-Lovelace) configuration data stored in `.storage` folder besides of yaml configuration. | UI flag
Report location | Report location and filename. | `/config/watchman_report.txt`
Custom header for the report | Custom header for watchman report. | `-== Watchman Report ==-`
Report's column width | Report's columns width. The list of column widths for the table version of the report. | `30, 7, 60`
Add friendly names | Add friendly name of the entity to the report whenever possible. | UI flag

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

> [!NOTE]
> Versions prior to 0.6.4 had report parameter named `service`, now it is renamed to `action`. Old parameter name still supported to preserve compatibilty with existing automations.

Parameter | YAML key | Description | Default
------------ | ------------- | -------------| -------------
Force configuration parsing |`parse_config`| Forces watchman to parse Home Assistant configuration files and rebuild entity and actions list. Usually this is not required as watchman will automatically parse files once Home Assistant restarts or tries to reload its configuration. | `False`
Send report as notification |`action`| Home assistant notification action to send report via, e.g. `persistent_notification.create`. See compatibility note below.| ``
Notification action data |`data`| A json object with additional notification action parameters. See [example](https://github.com/dummylabs/thewatchman#send-report-via-telegram-bot) below.  | `None`
Message chunk size |`chunk_size`| Maximum message size in bytes. Some notification actions, e.g., Telegram, refuse to deliver a message if its size is greater than some internal limit. If report text size exceeds `chunk_size`, the report will be sent in several subsequent notifications. `0` value will disable chunking. | `3500`


### A useless example sending report as persitent notification
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

Besides of the report, integration provides a few sensors which can be used within automations or dashboards:
- sensor.watchman_missing_entities
- sensor.watchman_missing_actions
- sensor.watchman_last_updated


## Example of a watchman report
Please note that the ASCII table format is only used when report is saved to a file. For notification actions watchman uses plain text list due to presentation limitations.
```
-== WATCHMAN REPORT ==-

-== Missing 1 action(s) from 38 found in your config:
+--------------------------------+---------+------------------------------------------+
| Action                         | State   | Location                                 |
+--------------------------------+---------+------------------------------------------+
| xiaomi_miio.vacuum_goto        | missing | automations.yaml:599,605                 |
+--------------------------------+---------+------------------------------------------+

-== Missing 3 entity(ies) from 216 found in your config:
+--------------------------------+---------+------------------------------------------+
| Entity                         | State   | Location                                 |
+--------------------------------+---------+------------------------------------------+
| sensor.stats_pm25_10_median    | unavail | customize.yaml:14                        |
| sensor.xiaomi_miio_sensor      | unavail | automations.yaml:231,1348                |
| vacuum.roborock_s5max          | unavail | automations.yaml:589,603,610,1569        |
+--------------------------------+---------+------------------------------------------+

-== Report created on 03 Feb 2022 17:18:55
-== Parsed 200 files in 0.96s., ignored 66 files
-== Generated in: 0.01s. Validated in: 0.00s.
```
The legend at the bottom of the report shows time consumed by 3 coherent stages: parse configuration files, validate each entity/action state and generate text version of the report.

## Markdown card example
Watchman sensors `sensor.watchman_missing_entities` and `sensor.watchman_missing_actions` have additional set of attributes which makes it possible to create your own report using a lovelace card. Below is an example of missing entities report for the Lovelace markdown card.
> [!NOTE]
> For dark mode replace /icon.png to /dark_logo.png.

```yaml
type: markdown
content: >-
  <h2> <img src="https://brands.home-assistant.io/watchman/icon.png" alt="WM Logo" width="32" height="32"> Watchman report</h2>
  <h3>Missing Entities: {{ states.sensor.watchman_missing_entities.state }} </h3>
  {%- for item in state_attr("sensor.watchman_missing_entities", "entities") %}
  <hr> <table><tr> <td>
  <ha-icon icon='mdi:
  {%- if item.state=="missing"-%}cloud-alert'
  {%- elif item.state=="unavail" -%}cloud-off-outline' {%- else-%}cloud-question'
  {%- endif -%} ></ha-icon>
  {{ item.id }} [{{item.state}}] <a title="{{item.occurrences}}">
  {{item.occurrences.split('/')[-1].split(':')[0]}}</a>
  </td></tr></table>
  {%- endfor %}
card_mod:
  style:
    ha-markdown:
      $: |
        ha-markdown-element:first-of-type hr{
          border-color: #303030;
        }

```
Important considerations:
1. Make sure you are in code editor mode before pasting this code into the markdown card
2. `card_mod` section is optional and requires a [custom lovelace card](https://github.com/thomasloven/lovelace-card-mod) to be installed for extra styling
3. Put mouse pointer over a file name to see full path to a file and line numbers
4. To display line numbers in the report just remove `.split(':')[0]` from the card template

<img src="https://raw.githubusercontent.com/dummylabs/thewatchman/main/images/markdown_card_example.png" width=50%>

The code for the actions report looks very similar:

```yaml
type: markdown
content: >-
  <h2> <img src="https://brands.home-assistant.io/watchman/icon.png" alt="WM Logo" width="32" height="32"> Watchman report</h2>
  <h3> Missing actions: {{ states.sensor.watchman_missing_actions.state }} </h3>
  {%- for item in state_attr("sensor.watchman_missing_actions", "entities") %}
  <hr><table><tr> <td>  <ha-icon icon='mdi:cloud-alert'></ha-icon> {{ item.id }}
  <a title="{{item.occurrences}}">{{item.occurrences.split('/')[-1].split(':')[0]}}</a>
  </td></tr></table>
  {%- endfor %}
card_mod:
  style:
    ha-markdown:
      $: |
        ha-markdown-element:first-of-type hr{
          border-color: #303030;
        }
```

[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=popout
[forum]: https://community.home-assistant.io/t/watchman-keeps-track-of-missing-entities-and-services-in-your-config-files/390391
