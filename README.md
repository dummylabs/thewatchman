# The Watchman
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)
![version](https://img.shields.io/github/v/release/dummylabs/thewatchman)
[![Community Forum][forum-shield]][forum]

The world around us is constantly changing and so is Home Assistant. How often have you found yourself in a situation when your automations had stopped working because some entities become permanently unavailable or actions changed their names? For example, Home Assistant companion app can easily change the name of its actions and sensors it exposes to Home Assistant if you changed the device name in the app configuration. The watchman is an attempt to control such unwelcome changes and make you able to react proatively, before some critical automation gets broken.

[Discussion on Home Assistant Community Forum](https://community.home-assistant.io/t/watchman-keeps-track-of-missing-entities-and-services-in-your-config-files/390391)

## Quick start

1. Go to the "Integrations" section on HACS, click "Explore and download repositories" and search for "watchman", then click "Download this repository with HACS".
2. Restart Home Assistant, go to Settings->Devices & Services->Add Integration and select Watchman integration. If integration not found, try to empty your browser cache and reload page.
3. Go to Developer Tools -> Actions, type `watchman` and select `Watchman: report` action then press "Perform Action" button. Check `watchman_report.txt` file in your configuration directory.

Refer to the [Configuration section](https://github.com/dummylabs/thewatchman#configuration) for further fine-tuning.

## What does it do
The watchman is a custom integration for Home Assistant, which collects all the Home Assistant entities (sensors, timers, input_selects, etc.) mentioned in your yaml configuration files as well as all the actions. Having a list of all entities, the integration checks their actual state one by one and reports those are not available or missing. For actions it checks whether action is available in the HA actions registry. The report can be stored as a nice-looking text table or it can be sent via notification action of choice (unless it is missing too :). The [example of a report](https://github.com/dummylabs/thewatchman#example-of-a-watchman-report) is given below.

The integration has very simple internals, it knows nothing about complex relationships and dependencies among yaml configuration files as well as nothing about the semantics of entities and automations. It parses yaml files line by line and tries to guess references either to an entity or to an action, based on the regular expression heuristics. The above means the integration can give both false positives (something which looks like a duck, swims like a duck, and quacks like a duck, but is not) and false negatives (when some entity in a configuration file was not detected by the integration). To ignore false positives **Ignored entities and services** parameter can be used (see Configuration section below), improvements for false negatives are a goal for future releases.

## What is does not do
The watchman will not report all available or missing entities within your system—only those that are actively used by Home Assistant, whether it is an automations, dashboard configuration, template sensor, etc.

## Configuration
> [!NOTE]
> Be aware of a minor confusion between the terms "Action" and "Service." Services were [renamed](https://developers.home-assistant.io/blog/2024/07/16/service-actions/) to Actions in mid-2024. However, parts of the Watchman UI still use the old term "Service." Therefore, the configuration examples below continue to use "Service" until the new version of Watchman addresses this.


Integration settings are available in Settings->Devices & Services->Watchman->Configure

[![Open your Home Assistant instance and show your integrations.](https://my.home-assistant.io/badges/integrations.svg)](https://my.home-assistant.io/redirect/integrations/)

Option | Description | Default
------------ | ------------- | -------------
Notification service | Home assistant notification action to send report via, e.g. `notify.telegram`. | `None`
Notification service data | A json object with additional notification action parameters. See [example](https://github.com/dummylabs/thewatchman#send-report-via-telegram-bot) below.  | `None`
Included folders | Comma-separated list of folders to scan for entities and actions recursively. | `/config`
Custom header for the report | Custom header for watchman report. | `"-== Watchman Report ==-"`
Report location | Report location and filename. | `"/config/watchman_report.txt"`
Ignored entities and services | Comma-separated list of items to ignore. The entity/action will be excluded from the report if their name matches a rule from the ignore list. Wildcards are supported, see [example](https://github.com/dummylabs/thewatchman#ignored-entities-and-services-option-example) below. | `None`
Ignored entity states | Comma-separated list of entity states which should be excluded from the report. Possible values are: `missing`, `unavailable`, `unknown`. | `None`
Message chunk size | Maximum message size in bytes. Some notification actions, e.g., Telegram, refuse to deliver a message if its size is greater than some internal limit. If report text size exceeds `chunk_size`, the report will be sent in several subsequent notifications. `0` value will disable chunking. | `3500`
Ignored files | Comma-separated list of files and folders to ignore. Wildcards are supported, see [example](https://github.com/dummylabs/thewatchman#ignored-files-option-example) below. Takes precedence over *Included folders* option.| `None`
Report's column width | Report's columns width. The list of column widths for the table version of the report. | `30, 7, 60`
Startup delay | By default, watchman's sensors are updated by `homeassistant_started` event. Some integrations may require extra time for intiialization so that their entities/actions may not yet be ready during watchman check. This is especially true for single-board computers like Raspberry PI. This option allows to postpone startup sensors update for certain amount of seconds. | `0`
Add friendly names | Add friendly name of the entity to the report whenever possible. | `False`
Parse dashboards UI | Parse Dashboards UI (ex-Lovelace) configuration data stored in `.storage` folder besides of yaml configuration. | `False`


### Ignored files option example
* Ignore a file: `*/automations.yaml`
* Ignore all files in the folder: `/config/esphome/*`
* Ignore several folders: `/config/custom_components/*, /config/appdaemon/*, /config/www/*`
<img src="https://raw.githubusercontent.com/dummylabs/thewatchman/main/images/ignored_files_ui.png" width=50%>

### Ignored entities and actions (formely known as 'services') option example
* Ignore an entity: `person.dummylabs`
* Ignore everything in sensor domain: `sensor.*`
* Ignore any entity/service which name ends with "_ble": `*.*_ble`

### Send report via telegram bot
* *Notification service*: `telegram_bot.send_message`
* *Notification service data*: `{"parse_mode":"html"}`

## Watchman.report action
The text version of the report can be generated using `watchman.report` action from Developer Tools UI, an automation or a script. Default location is `/config/thewatchman_report.txt`, which can be altered by `report_path` configuration option. A long report will be split into several messages (chunks) due to limitations imposed by some notification actions (e.g., telegram). Action behaviour can be altered with additional optional parameters:

 - `create_file` create text version of the report (optional, default=true)
 - `send_notification` send report via notification action (optional, default=false)
 - `service` notification action name (optional, overrides eponymous parameter from integration settings)
 - `data` notification action data (optional, overrides eponymous parameter from integration settings)
 - `parse_config` see below (optional, default=false)
 - `chunk_size` (optional, default is 3500 or whatever specified in integration settings)

The parameter `service` allows sending report text via notification action of choice. Along with `data` and `chunk_size` it overrides integration settings.

`parse_config` forces watchman to parse Home Assistant configuration files and rebuild entity and actions list. Usually this is not required as watchman will automatically parse files once Home Assistant restarts or tries to reload its configuration.
Also see [Advanced usage examples](https://github.com/dummylabs/thewatchman#advanced-usage-examples) section at the bottom of this document.

### Call action from Home Assistant UI
<img src="https://raw.githubusercontent.com/dummylabs/thewatchman/main/images/service_example.png" width=70%>


### Extra notification action parameters example
```yaml
action: watchman.report
create_file: false
data:
  service: telegram_bot.send_message
  data: # additional parameters for your notification service
    parse_mode: html
    target: 111111111 # can be omitted, see telegram_bot documentation
```

## Sensors
Besides of the report, a few sensors will be added to Home Assistant:

- sensor.watchman_missing_entities
- sensor.watchman_missing_services
- sensor.watchman_last_updated

## Example of a watchman report
Please note that the ASCII table format is only used when report is saved to a file. For notification actions watchman uses plain text list due to presentation limitations.
```
-== WATCHMAN REPORT ==-

-== Missing 1 service(s) from 38 found in your config:
+--------------------------------+---------+------------------------------------------+
| Service                        | State   | Location                                 |
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
Watchman sensors `sensor.watchman_missing_entities` and `sensor.watchman_missing_services` have additional set of attributes which makes it possible to create your own report using a lovelace card. Below is an example of missing entities report for the Lovelace markdown card:

```yaml
type: markdown
content: >-
  <h2> <ha-icon icon='mdi:shield-half-full'></ha-icon> Watchman report</h2>
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
  <h2 class="some"> <ha-icon icon='mdi:shield-half-full'></ha-icon> Watchman report</h2>
  <h3> Missing actios: {{ states.sensor.watchman_missing_services.state }} </h3>
  {%- for item in state_attr("sensor.watchman_missing_services", "entities") %}
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

### Exclude Watchman from the recorder

If you encounter a warning from the Recorder component "State attributes for sensor.watchman_missing_entities exceed maximum size of 16384 bytes" you can exclude these using following configuration:

```yaml
# Don't include watchman results in recorder as they're too big!
recorder:
  exclude:
    entities:
      - sensor.watchman_missing_entities
      - sensor.watchman_missing_services
```
There is the ticket #87 addressing this issue.

## Advanced usage examples

### Additional notification action parameters
Notification action name can be specified in integration options along with additional action parameters.
#### UI settings example
<img src="https://raw.githubusercontent.com/dummylabs/thewatchman/main/images/service_data_ui.png" width=50%>

### Additional notification action parameters in Watchman:report action
You can use an arbitrary notification action with `watchman.report` action. Action paramaters takes precedence over eponymous UI settings.
```yaml
action: watchman.report
data:
  service: telegram_bot.send_message
  data:
    title: Hello
    parse_mode: html
```

### Send report as a text file via telegram bot
You should add report folder to the Home Assistant whitelist, otherwise telegram_bot will be unable to pick files from the folder (see example configuration below).
```yaml
action: watchman.report
data:
  service: telegram_bot.send_document
  data:
    file: '/config/thewatchman_report.txt'
```
:warning: Whitelisting the configuration folder can be unsafe, use it at your own risk or put report file in a separate folder.
```yaml
homeassistant:
  allowlist_external_dirs:
    - /config/
```

[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=popout
[forum]: https://community.home-assistant.io/t/watchman-keeps-track-of-missing-entities-and-services-in-your-config-files/390391
