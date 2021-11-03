# Amazon Personalize Filter Rotation

This project contains the source code and supporting files for deploying a serverless application that provides automatic [filter](https://docs.aws.amazon.com/personalize/latest/dg/filter.html) rotation capabilities for [Amazon Personalize](https://aws.amazon.com/personalize/), an AI service from AWS that allows you to create custom ML recommenders based on your data. Highlights include:

- Automatically creates filters based on a filter naming template you provide
- Automatically formats the filter expression based on filter expression template you provide
- Automatically deletes filters based on a dynamic matching expression you provide

## <a name='Whyisthisimportant'></a>Why is this important?

Amazon Personalize filters are a great way to have your business rules applied to recommendations before they are returned to your application. They can be used to include or exclude items from being recommended for a user based on a SQL-like syntax that considers the user's interaction history, item metadata, and user metadata. For example, only recommend movies that the user has watched or favorited in the past to populate a "Watch again" widget.

```
INCLUDE ItemID WHERE Interactions.event_type IN ('watched','favorited')
```

Or exclude products from being recommended that are currently out of stock.

```
EXCLUDE ItemID WHERE Items.out_of_stock IN ('yes')
```

You can even use dynamic filters where the filter expression values are specified at runtime. For example, only recommend movies for a specific genre.

```
INCLUDE ItemID WHERE Items.genre IN ($GENRES)
```

To use the filter above, you would pass the appropriate value(s) for the `$GENRE` variable when retrieving recommendations.

Filters are great! However, they do have some limitations. One of those limitations is being able to specify a dynamic value for a range query. For example, the following filter to limit recommendations to new items that were created since a rolling point in the past is **not** supported.

**THIS WON'T WORK!**
```
INCLUDE ItemID WHERE Items.creation_timestamp > $NEW_ITEM_THRESHOLD
```

The solution to this limitation is to use a filter expression with a hard-coded value for range queries.

**THIS WORKS!**
```
INCLUDE ItemID WHERE Items.creation_timestamp > 1633240824
```

However, this is not very flexible or maintainble since time marches on but your filter expression does not. The workaround is to update your filter expression periodically to maintain a rolling window of time. Unfortunately filters cannot be updated so a new filter has to be created, you application has to transition to using the new filter, and then the previous filter can be deleted.

The purpose of this serverless application is to make this easier to maintain by automating the creation and deletion of filters and allowing you to provide a dynamic expression that is resolved to the appropriate hard-coded value when the new filter is created.

## <a name='Hereshowitworks'></a>Here's how it works

An AWS Lambda function is deployed by this application that is called on a recurring basis. You control the schedule which can be a cron expression or a rate expression. The function will only create a new filter and delete existing filters if a filter does not exist that matches the current filter name template and if any filters match the delete template, respectively. Therefore, it is fine to have the function run more often than necessary (i.e. if you don't have a predictable and consistent time when filters should be rotated).

The key to the filter rotation filter are the templates used to verify that the current template exists and if existing template(s) are eligible to delete. Let's look at some examples.

### <a name="Currentfilternametemplate"></a>Current filter name template

Let's say you want to use a filter that only recommends recently created items. The `CREATION_TIMESTAMP` column in the items dataset is a convenient field to use for this. This column name is reserved and is used to support the cold item exploration feature of the `aws-user-personalization` recipe. Values must be expressed in the Unix timestamp format as `long`'s (i.e. number of seconds since the Epoch). The following expression limits items that were created in the last month (`1633240824` is the Unix timestamp from 1 month ago as of this writing).

```
INCLUDE ItemID WHERE Items.creation_timestamp > 1633240824
```

Alternatively, you can use a custom metadata column for the filter that uses a more coarse and/or human readable format but is still comparable for range queries, like YYYYMMDD.

```
INCLUDE ItemID WHERE Items.published_date > 20211001
```

As noted earlier, filters cannot be updated. Therefore we can't just change the filter expression of the filter. Instead, we have to create a new filter with a new expression, switch our application to use the new filter, and then delete the old filter. This requires using a predictable naming standard for filters so applications can automatically switch to using the new filter without a coding change. Continuing with the creation timestamp theme, the filter name could be something like.

```
filter-include-recent-items-20211101
```

Assuming we want to rotate this filter each day, the next day's filter name would be `filter-include-recent-items-20211004`, then `filter-include-recent-items-20211005`, and so on. What is needed is a template that defines the filter name that can be resolved when the rotation script runs.

```
filter-include-recent-items-{{datetime_format(now,'%Y%m%d')}}
```

The above filter name template will resolve and replace the expression within the `{{` and `}}` characters (handlebars or mustaches). In this case, we are taking the current time expressed as `now` and formatting it using the `%Y%m%d` date format expression. The result (as of today) is `20211102`. If the rotation function finds an existing filter with this name, a new filter does not need to be created. Otherwise, a new filter is created using `filter-include-recent-items-20211102` as the name.

The `PersonalizeCurrentFilterNameTemplate` CloudFormation template parameter is how you specify your own custom filter name template.

There are a number of built-in default values and functions that are available to use in templates. However, for security reasons, the supported functions are tightly controlled to prevent abuse.

### <a name="Currentfilterexpressiontemplate"></a>Current filter expression template

When rotating and creating the new filter, we also may have to dynamically resolve the actual filter expression. The `PersonalizeCurrentFilterExpressionTemplate` CloudFormation template parameter can be used for this. Some examples.

```
INCLUDE ItemID WHERE Items.CREATION_TIMESTAMP > {{int(unixtime(now - timedelta_days(30)))}}
```

```
INCLUDE ItemID WHERE Items.published_date > {{datetime_format(now - timedelta_days(30),'%Y%m%d')}}
```

### <a name="Deletefiltermatchtemplate"></a>Delete filter match template

Finally, we need to clean up old filters after we have transitioned to a newer version of the filter. A filter name matching template can be used for this and can be written in such a way to delay the delete for some time after the new filter is created. This gives your application time to transition from the old filter to the new filter. The `PersonalizeDeleteFilterMatchTemplate` CloudFormation template parameter is where you specify the delete filter match template.

The following delete filter match template will match on filters with a filter name that starts with `filter-include-recent-items-` and has a suffix is more than one day older than today. In other words, we have 1 day to transition to the new filter before the old filter is deleted.

```
starts_with(filter.name,'filter-include-recent-items-') and int(end(filter.name,8)) < int(datetime_format(now - timedelta_days(1),'%Y%m%d'))
```

Any filters that trigger this template to resolve to `true` will be deleted. All others will be left alone. Note that all fields available in the [FilterSummary](https://docs.aws.amazon.com/personalize/latest/dg/API_FilterSummary.html) of the [ListFilters API](https://docs.aws.amazon.com/personalize/latest/dg/API_ListFilters.html) response are available in the template. For example, the template above matches on `filter.name`. Other filter summary fields such as `filter.status`, `filter.creationDateTime`, and `filter.lastUpdatedDateTime` can also be inspected in the template.

## <a name='Filtertemplatesyntax'></a>Filter template syntax

The [Simple Eval](https://github.com/danthedeckie/simpleeval) library is used as the foundation of for the template syntax. Check the Simple Eval library documentation for details on the functions available.

The following additional functions were add as part of this application to make writing templates easier.

- `unixtime(value)`: Returns the Unix timestamp value given a string, datetime, date, or time. If a string is provided, it will be parsed into a datetime first.
- `datetime_format(date, pattern)`: Formats a datetime, date, or time using the specified pattern.
- `timedelta_days(int)`: Returns a timedelta for a number of days. Can be used for date math.
- `timedelta_hours(int)`: Returns a timedelta for a number of hours. Can be used for date math.
- `timedelta_minutes(int)`: Returns a timedelta for a number of minutes. Can be used for date math.
- `timedelta_seconds(int)`: Returns a timedelta for a number of seconds. Can be used for date math.
- `starts_with(str, prefix)`: Returns True if the string value starts with prefix.
- `ends_with(str, suffix)`: Returns True if the string value ends with suffix.
- `start(str, num)`: Returns the first num characters of the string value
- `end(str, num)`: Returns the last num characters of the string value
- `now`: Current datetime

## <a name='Installingtheapplication'></a>Installing the application

***IMPORTANT NOTE:** Deploying this application in your AWS account will create and consume AWS resources, which will cost money. The Lambda function is called according to the schedule you provide but typically should not need to be called more often than hourly. Personalize does not charge filters but your account does have a limit on the number of filters that are active at any time. There are also limits on how many filers can be in a pending or in-progress status. Therefore, if after installing this application you choose not to use it as part of your monitoring strategy, be sure to follow the Uninstall instructions in the next section to avoid ongoing charges and to clean up all data.*

This application uses the AWS [Serverless Application Model](https://aws.amazon.com/serverless/sam/) (SAM) to build and deploy resources into your AWS account.

To use the SAM CLI, you need the following tools.

* SAM CLI - [Install the SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)
* [Python 3 installed](https://www.python.org/downloads/)
* Docker - [Install Docker community edition](https://hub.docker.com/search/?type=edition&offering=community)

To build and deploy the application for the first time, run the following in your shell:

```bash
sam build --use-container --cached
sam deploy --guided --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND
```

If you receive an error from the first command about not being able to download the Docker image from `public.ecr.aws`, you may need to login. Run the following command and then retry the above two commands.

```bash
aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws
```

The first command will build the source of the application. The second command will package and deploy the application to your AWS account, with a series of prompts:

| Prompt/Parameter | Description | Default |
| --- | --- | --- |
| Stack Name | The name of the stack to deploy to CloudFormation. This should be unique to your account and region. | `personalize-filter-rotator` |
| AWS Region | The AWS region you want to deploy this application to. | Your current region |
| Parameter PersonalizeDatasetGroupArn | Amazon Personalize dataset group ARN to rotate filters within. | |
| Parameter PersonalizeCurrentFilterNameTemplate | Template to use when checking and creating the current filter. | |
| Parameter PersonalizeCurrentFilterExpressionTemplate | Template to use when building the filter expression when creating the current filter. | |
| Parameter PersonalizeDeleteFilterMatchTemplate (optional) | Template to use to match existing filters that should be deleted. | |
| Parameter RotationSchedule | Cron or rate expression to control how often the rotation function is called. | `rate(1 hours)` |
| Confirm changes before deploy | If set to yes, any CloudFormation change sets will be shown to you before execution for manual review. If set to no, the AWS SAM CLI will automatically deploy application changes. | |
| Allow SAM CLI IAM role creation | Since this application creates IAM roles to allow the Lambda functions to access AWS services, this setting must be `Yes`. | |
| Save arguments to samconfig.toml | If set to yes, your choices will be saved to a configuration file inside the application, so that in the future you can just re-run `sam deploy` without parameters to deploy changes to your application. | |

## <a name='Uninstallingtheapplication'></a>Uninstalling the application

To remove the resources created by this application in your AWS account, use the AWS CLI. Assuming you used the default application name for the stack name (`personalize-filter-rotator`), you can run the following:

```bash
aws cloudformation delete-stack --stack-name personalize-filter-rotator
```

Alternatively, you can delete the stack in CloudFormation in the AWS console.

## <a name='Reportingissues'></a>Reporting issues

If you encounter a bug, please create a new issue with as much detail as possible and steps for reproducing the bug. Similarly, if you have an idea for an improvement, please add an issue as well. Pull requests are also welcome! See the [Contributing Guidelines](./CONTRIBUTING.md) for more details.

## <a name='Licensesummary'></a>License summary

This sample code is made available under a modified MIT license. See the LICENSE file.
