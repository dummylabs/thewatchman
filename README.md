# The Watchman

The world around us is constantly changing and so is Home Assistant. How often have you found yourself in a situation when your automations had stopped working because some entities become permanently unavailable or services changed their name? For example, Home Assistant companion app can easily change the name of its services and sensors it exposes to Home Assistant if you changed the device name in the app configuration. The watchman is an attempt to control such changes and make you able to react proactively, before some critical automation gets broken.

## Quick start

1. Go to the "Integrations" section on HACS, tap the three-dots menu in the upper right corner, go to "Custom repositories". Add new repository `dummylabs/thewatchman` with **Integration** category. 
2. Click the big blue button "Explore and download repositories" and search for "watchman", then click "Download this repository with HACS".
3. Restart Home Assistant and add `watchman` section to `configuration.yaml` file.
```yaml
watchman:
```
4. Restart Home Assistant again, go to Developer Tools -> Services, type `watchman` and select `Watchman: report` service then press "Call Service" button. Check `thewatchman_report.txt` file in your configuration directory.

Refer to the [Configutation section](https://github.com/dummylabs/thewatchman#configuration) for the fine tuning.

## What does it do
The watchman is a custom integration for Home Assistant, which collects all the Home Assistant entities (sensors, timers, input_selects, etc.) mentioned in your yaml configuration files as well as all the services. Having a list of all entities, the app checks their actual state one by one and reports those are not available or missing. For services it checks whether service is available in the HA service registry. The report can be stored as a nice looking text table or it can be send via notification service of choice (unless it is missing too :). The [example of a report](https://github.com/dummylabs/thewatchman#example-of-a-watchman-report) is given below. 

The integration has very simple internals, it knows nothing about complex relationships and dependencies among yaml configuration files as well as nothing about the semantics of entities and automations. It parses yaml files line by line and tries to guess references either to an entity or to a service, based on the regular expression heuristics. The above means the integration can give both false positives (something which looks like a duck, swims like a duck, and quacks like a duck, but is not) and false negatives (when some entity in a configuration file was not detected by the integration). To ignore false positives `ignored_items` parameter can be used (see Configuration section below), improvements for false negatives are a goal for future releases. 


## Configuration

### Options:

Key | Required | Description | Default 
------------ | ------------- | ------------- | ------------- 
`service` | False | Home assistant notification service to sent report via, e.g. `notify.telegram`  | `None` 
`data` | False| A yaml dictionary with additional notification service parameters, see [Advanced usage examples](https://github.com/dummylabs/thewatchman#additional-notification-service-parameters-in-configurationyaml) below
`included_folders` | False | List of folders to scan for entities and services recursively | `"/config"`
`report_header` | False | Custom header for watchman report | `"-== Watchman Report ==-"`
`report_path` | False | Report file location | `"/config/watchman_report.txt"`
`ignored_items` | False | List of items to ignore. The entity/service will be excluded from the report if their name matches a rule from the ignore list. Wildcards are supported, see [Advanced Configuration](https://github.com/dummylabs/thewatchman#advanced-configuration-example) example below. | `None`
`ignored_states` | False | List of entity states which should be excluded from the report. Possible values are: `missing`, `unavailable`, `unknown` | `None`
`chunk_size` | False | Some notification services, e.g., Telegram, refuse to deliver a message if its size is greater than some internal limit. This key allows to set average size of a message in bytes. If report text size exceeds `chunk_size`, the report will be sent in several subsequent notifications | `3500`
`ignored_files` | False | Allows to ignore a specific file or a whole folder using wildcards, see [Advanced usage examples below](https://github.com/dummylabs/thewatchman#exclude-specific-file-or-folder-from-the-report). Takes precedence over `included_folders`.| `None`
`check_lovelace` | False | Parse Lovelace UI configuration data stored in `.storage` folder (experimental) | `False`
`columns_width` | False | The list of column widths for text version of the report | `[30, 7, 60]`
`startup_delay` | False | By default, watchman's sensors are updated by `homeassistant_started` event. Some integrations may require extra time for intitialization so that their entities/services may not yet be ready during watchman check. This is especially true for single-board computers like Raspberry PI. This option allows to postpone startup sensors update for certain amount of seconds. | `0`
`friendly_names` | False | Add friendly names to the report whenever possible | `False`


### Configuration example

```yaml
watchman:
  ignored_files: 
    - "*/automations.yaml" # a file (entries with leading wildcards must be enclosed in quotes)
    - /config/esphome/* # a whole folder
    - /config/custom_components/*
    - /config/appdaemon/*
    - /config/www/*
  service: telegram_bot.send_message
  data:
    parse_mode: html
  report_path: /config/report.txt
  chunk_size: 2000
  ignored_items: 
    - person.dummylabs
    - sensor.* # ignore everything in sensor domain 
    - "*.*_ble"  # ignore any entity/service which name ends with "_ble" 
  ignored_states:
    - unknown
```

## Watchman.report service

The report can be created by calling `watchman.report` service from Developer Tools UI, an automation or a script. Default location is `/config/thewatchman_report.txt`, it can be altered by `report_path` configuration option. 
If no parameters were set, the service will create a text report and send a notification via notification service from configuration option `service`. A long report will be split into several messages (chunks) due to limitations imposed by some notification services (e.g., telegram). Service behavior can be altered with additional parameters:

 - `create_file` (optional, default=true)
 - `send_notification` (optional, default=true)
 - `service` (optional, overrides eponymous parameter from `configuration.yaml`)
 - `data`(optional, overrides eponymous parameter from `configuration.yaml`)
 - `parse_config` (optional, default=false)
 - `chunk_size` (optional, default is 3500 or whatever specified in `configuration.yaml`)

If `create_file` or `send_notification` flags were not set, they are `true` by default. The parameter `service` allows sending report text via notification service of choice. Along with `data` and `chunk_size` it overrides settings from `configuration.yaml` file.

`parse_config` forces watchman to parse Home Assistant configuration files and rebuild entity and services list. Usually this is not required as watchman will automatically parse files once Home Assistant restarts or tries to reload its configuration.
Also see [Advanced usage examples](https://github.com/dummylabs/thewatchman#advanced-usage-examples) section at the bottom of this document. 

### Call service from Home Assistant UI
![service example](./images/service_example.png)

### Extra notification service parameters example
```yaml
service: watchman.report
create_file: false
data:
  service: telegram_bot.send_message
  data: # additional parameters for your notification service
    parse_mode: html
    target: 111111111 # can be omitted, see telegram_bot documentation
```


Besides of the report, a few sensors will be automatically created or updated:

- sensor.watchman_missing_entities
- sensor.watchman_missing_services
- sensor.watchman_last_updated

## Example of a watchman report
Please note that the ASCII table format is only used when report is saved to a file. For notification services watchman uses plain text list due to presentation limitations.
```
-== WATCHMAN REPORT ==-  

-== Missing 1 service(-s) from 38 found in your config:
+--------------------------------+---------+------------------------------------------+
| Service                        | State   | Location                                 |
+--------------------------------+---------+------------------------------------------+
| xiaomi_miio.vacuum_goto        | missing | automations.yaml:599,605                 |
+--------------------------------+---------+------------------------------------------+

-== Missing 3 entity(-es) from 216 found in your config:
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
The legend at the bottom of the report shows time consumed by 3 coherent stages: parse configuration files, validate each entity/service state and generate text version of the report.

## Advanced usage examples

### Additional notification service parameters in configuration.yaml
Notification service can be specified in extended format along with additional service parameters.
```yaml
watchman:
  service: telegram_bot.send_message
  data:
    title: Hello
    parse_mode: html
```

### Additional notification service parameters in Watchman: report service
You can use an arbitrary notification service with `watchman.report` service. Service paramaters takes precedence over eponymous settings in `configuration.yaml`.
```yaml
service: watchman.report
data:
  service: telegram_bot.send_message
  data:
    title: Hello
    parse_mode: html
```

### Send report as a text file via telegram bot
You should add report folder to the Home Assistant whitelist, otherwise telegram_bot will be unable to pick files from the folder (see example configuration below). 
```yaml
service: watchman.report
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

### Exclude specific file or folder from the report
Specific files or even whole folders can be excluded from the report using wildcards, see example below. Wildcards in configuration file should be enclosed in quotes. This is more powerful alternative to `excluded_folders` parameter which will be deprecated in the future.
```yaml
watchman:
  ignored_files:
    # wildcards must be enclosed in quotes!
    - "*.yaml" # exclude all yaml files from the report
    - "/config/entities/*" # exclude all files in /config/entities
    - "*/automations.yaml" # exclude automations.yaml file only
```