# Allowed imports: see https://cloud.google.com/deployment-manager/docs/configuration/templates/import-python-libraries

import typing


class Variables(object):
    """Variables exists so that Deployment Manager properties (equivalent to Terraform variables) aren't strings.
    """

    def __init__(self) -> None:
        self.name = ""
        self.labels = {}
        self.pubsub_ack_deadline_seconds = 0
        self.logging_filter = ""
        self.logging_exclusions = []
        self.pubsub_message_retention_duration = ""
        self.pubsub_minimum_backoff = ""
        self.pubsub_maximum_backoff = ""
        self.project_id = ""
        self.region = ""
        self.enable_extensions = False


def get_variables(context) -> Variables:
    # context object info:
    # https://cloud.google.com/deployment-manager/docs/configuration/syntax-reference#template_properties
    # https://cloud.google.com/deployment-manager/docs/configuration/syntax-reference#deployment-specific_environment_variables

    var = Variables()

    properties = {}
    if context.properties is not None:
        properties = context.properties

    var.name = properties.get("name", "observe-collection")
    if len(var.name) > 20:
        raise Exception("The name must be less than 20 characters long.")
    var.labels = properties.get("labels", {})
    var.pubsub_ack_deadline_seconds = properties.get(
        "pubsub_ack_deadline_seconds", 60)
    var.logging_filter = properties.get("logging_filter", "")
    var.logging_exclusions = properties.get("logging_exclusions", [])
    var.pubsub_message_retention_duration = properties.get(
        "pubsub_message_retention_duration", "86400s")
    var.pubsub_minimum_backoff = properties.get(
        "pubsub_minimum_backoff", "10s")
    var.pubsub_maximum_backoff = properties.get(
        "pubsub_maximum_backoff", "600s")
    var.enable_extensions = properties.get("enable_extensions", True)

    var.project_id = properties["project_id"]  # required
    var.region = properties["region"]  # required

    return var


class Locals(object):
    def __init__(self, vars: Variables) -> None:
        self.project = vars.project_id
        self.region = vars.region


class Resource:  # See https://cloud.google.com/deployment-manager/docs/configuration/syntax-reference#basic_syntax
    """Resource exists so I don't forget about metadata.dependsOn
    """

    def __init__(self, name: str, typ: str, properties: dict, metadata=None) -> None:
        self.name = name
        self.type = typ
        self.properties = properties
        self.metadata = metadata

    def as_dict(self) -> dict:
        d = {
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }
        if self.metadata is not None:
            d["metadata"] = self.metadata
        return d


def GenerateConfig(context):
    var = get_variables(context)
    local = Locals(var)

    resources: typing.List[dict] = []
    resources.append(Resource(
        "google_pubsub_topic-this",
        # REST API schema: https://cloud.google.com/pubsub/docs/reference/rest/v1/projects.topics
        # Schema override: gcloud beta deployment-manager type-providers describe pubsub-v1 --project gcp-types
        "gcp-types/pubsub-v1:projects.topics",
        {
            "topic": var.name,
            "labels": var.labels,
            "messageStoragePolicy": {
                "allowedPersistenceRegions": [local.region],
            },
        },
    ).as_dict())

    resources.append(Resource(
        "google_pubsub_subscription-this",
        # REST API schema: https://cloud.google.com/pubsub/docs/reference/rest/v1/projects.subscriptions
        # Schema override: gcloud beta deployment-manager type-providers describe pubsub-v1 --project gcp-types
        "gcp-types/pubsub-v1:projects.subscriptions",
        {
            # If you change this, you should also change the output subscription
            "subscription": var.name,
            "labels": var.labels,
            "topic": "$(ref.google_pubsub_topic-this.name)",
            "ackDeadlineSeconds": var.pubsub_ack_deadline_seconds,
            "messageRetentionDuration": var.pubsub_message_retention_duration,
            "retryPolicy": {
                "minimumBackoff": var.pubsub_minimum_backoff,
                "maximumBackoff": var.pubsub_maximum_backoff,
            },
        }).as_dict())

    resources.append(Resource(
        "google_logging_project_sink-this",
        # REST API schema: https://cloud.google.com/logging/docs/reference/v2/rest/v2/projects.sinks
        # Schema override: gcloud beta deployment-manager type-providers describe logging-v2 --project gcp-types
        "gcp-types/logging-v2:projects.sinks",
        {
            "parent": local.project,
            "name": var.name,
            "sink": var.name,
            "destination": f"pubsub.googleapis.com/$(ref.google_pubsub_topic-this.name)",
            "uniqueWriterIdentity": True,
            "filter": var.logging_filter,
            "description":  "Export logs to the Observe PubSub topic",
            "exclusions": var.logging_exclusions,
        },
    ).as_dict())

    resources.append(Resource(
        "google_pubsub_topic_iam_member-sink_pubsub",
        # Schema: gcloud beta deployment-manager type-providers describe cloudresourcemanager-v1 --project gcp-types
        "gcp-types/cloudresourcemanager-v1:virtual.projects.iamMemberBinding",
        {
            "resource": local.project,
            "role": "roles/pubsub.publisher",
            "member": "$(ref.google_logging_project_sink-this.writerIdentity)"
        }
    ).as_dict())

    resources.append(Resource(
        "google_service_account-poller",
        # REST API schema: https://cloud.google.com/iam/docs/reference/rest/v1/projects.serviceAccounts
        # Schema override: gcloud beta deployment-manager type-providers describe iam-v1 --project gcp-types
        "gcp-types/iam-v1:projects.serviceAccounts",
        {
            "accountId": f"{var.name}-poll",
            "description": "A service account for the Observe Pub/Sub and Logging pollers",
        },
    ).as_dict())

    for i, each_key in enumerate([
        "roles/pubsub.subscriber",
        "roles/monitoring.viewer",
        "roles/cloudasset.viewer",
        "roles/browser",
    ]):
        resources.append(Resource(
            f"google_project_iam_member-poller-{i}",
            # Schema: gcloud beta deployment-manager type-providers describe cloudresourcemanager-v1 --project gcp-types
            "gcp-types/cloudresourcemanager-v1:virtual.projects.iamMemberBinding",
            {
                "resource": local.project,
                "role": each_key,
                "member": "serviceAccount:$(ref.google_service_account-poller.email)"
            },
        ).as_dict())

    resources.append(Resource(
        "google_service_account_key-poller",
        # REST API schema: https://cloud.google.com/iam/docs/reference/rest/v1/projects.serviceAccounts.keys
        # Schema override: gcloud beta deployment-manager type-providers describe iam-v1 --project gcp-types
        "gcp-types/iam-v1:projects.serviceAccounts.keys",
        {
            "name": "poller",
            "parent": "$(ref.google_service_account-poller.name)"
        },
    ).as_dict())

    if var.enable_extensions:
        extension_var = get_extension_variables(
            project_id=var.project_id,
            region=var.region,
            topic_id="$(ref.google_pubsub_topic-this.name)",
            extensions_to_include=[
                "export-instance-groups",
                "export-service-accounts",
                "export-cloud-scheduler"
            ],
            name_format=f"{var.name}-%s",
        )
        extension_local = ExtensionLocals(extension_var)
        resources += extension_main(extension_var, extension_local)
        resources += extension_cloud_scheduler(extension_var, extension_local)

    return {
        "resources": resources,
        "outputs": [{
            "name": "subscription_id",
            "value": var.name,
        }, {
            "name": "poller_private_key_base64",
            "value": "$(ref.google_service_account_key-poller.privateKeyData)",
        }]
    }


class ExtensionVariables:
    def __init__(self) -> None:
        self.project_id = ""
        self.region = ""
        self.topic_id = ""
        self.name_format = ""
        self.extensions_to_include = []


def get_extension_variables(
    project_id: str,
    region: str,
    topic_id: str,
    extensions_to_include=[
        "export-instance-groups",
        "export-service-accounts",
        "export-cloud-scheduler"
    ],
    name_format="extension-%s",
) -> ExtensionVariables:
    v = ExtensionVariables()
    v.project_id = project_id
    v.region = region
    v.topic_id = topic_id
    v.extensions_to_include = extensions_to_include
    v.name_format = name_format
    return v


class ExtensionEntryPoint:
    def __init__(self, description, entry_point, dependent_roles) -> None:
        self.description = description
        self.entry_point = entry_point
        self.dependent_roles = dependent_roles


class ExtensionLocals:
    def __init__(self, var: ExtensionVariables) -> None:
        self.base_roles = [
            "roles/storage.objectViewer",
            "roles/pubsub.publisher",
        ]
        self.function_env_vars = {
            "PROJECT_ID": var.project_id,
            "TOPIC_ID": var.topic_id,
        }
        self.entry_point = {
            "export-instance-groups": ExtensionEntryPoint(
                description="function for exporting compute instance groups and thier instances",
                entry_point="list_instance_group",
                dependent_roles=["roles/compute.viewer"],
            ),
            "export-service-accounts": ExtensionEntryPoint(
                description="function for exporting service accounts",
                entry_point="list_service_accounts",
                dependent_roles=["roles/iam.serviceAccountViewer"],
            ),
            "export-cloud-scheduler": ExtensionEntryPoint(
                description="function for exporting cloud scheduler jobs",
                entry_point="list_cloud_scheduler_jobs",
                dependent_roles=["roles/cloudscheduler.viewer"],
            )
        }

        self.extensions = {
            k: v
            for k, v in self.entry_point.items()
            if k in var.extensions_to_include
        }
        self.extensions_roles: typing.List[str] = []
        for _, v in self.extensions.items():
            self.extensions_roles.extend(v.dependent_roles)
        self.roles = set(self.base_roles + self.extensions_roles)


def extension_main(var: ExtensionVariables, local: ExtensionLocals) -> typing.List[dict]:
    resources: typing.List[dict] = []
    resources.append(Resource(
        "google_service_account-cloud_functions",
        "gcp-types/iam-v1:projects.serviceAccounts",
        {
            "accountId": var.name_format % "pub-sub-func",
            "description":  "A service account for the Observe Cloud Functions",
        }
    ).as_dict())

    for each_key in local.roles:
        resources.append(Resource(
            f"google_project_iam_member-cloud_functions-{each_key}",
            # Schema: gcloud beta deployment-manager type-providers describe cloudresourcemanager-v1 --project gcp-types
            "gcp-types/cloudresourcemanager-v1:virtual.projects.iamMemberBinding",
            {
                "resource": var.project_id,
                "role": each_key,
                "member": "serviceAccount:$(ref.google_service_account-cloud_functions.email)"
            },
        ).as_dict())

    for each_key, each_value in local.extensions.items():
        resources.append(Resource(
            f"google_cloudfunctions_function-function-{each_key}",
            # Schema: gcloud beta deployment-manager type-providers describe cloudfunctions-v1 --project gcp-types
            "gcp-types/cloudfunctions-v1:projects.locations.functions",
            {
                "function": var.name_format % f"{each_key}-v2",
                "parent": f"projects/{var.project_id}/locations/{var.region}",
                "description": each_value.description,
                "serviceAccountEmail": "$(ref.google_service_account-cloud_functions.email)",
                "runtime": "python310",
                "environmentVariables": local.function_env_vars,
                "availableMemoryMb": 512,
                "sourceArchiveUrl": "gs://observeinc/google-cloud-functions.zip",
                "ingressSettings": "ALLOW_ALL",
                "timeout": "120s",
                "entryPoint": each_value.entry_point,
                "httpsTrigger": {
                    "securityLevel": "SECURE_ALWAYS",
                }
            },
        ).as_dict())
    return resources


def extension_cloud_scheduler(var: ExtensionVariables, local: ExtensionLocals) -> typing.List[dict]:
    """From terraform config in cloud_scheduler.tf"""
    resources: typing.List[dict] = []
    resources.append(Resource(
        "google_service_account-cloud_scheduler",
        "gcp-types/iam-v1:projects.serviceAccounts",
        {
            "accountId": var.name_format % "sched",
            "description":  "A service account to allow the Observe Cloud Scheduler job to trigger some Cloud Functions",
        }
    ).as_dict())

    resources.append(Resource(
        "google_project_iam_member-cloud_scheduler_cloud_function_invoker",
        "gcp-types/cloudresourcemanager-v1:virtual.projects.iamMemberBinding",
        {
            "resource": var.project_id,
            "role": "roles/cloudfunctions.invoker",
            "member": "serviceAccount:$(ref.google_service_account-cloud_scheduler.email)",
        }
    ).as_dict())

    for each_key, each_value in {k: v for k, v in local.entry_point.items()}.items():
        resources.append(Resource(
            f"google_cloud_scheduler_job-this-{each_key}",
            "gcp-types/cloudscheduler-v1:projects.locations.jobs",
            {
                "parent": f"projects/{var.project_id}/locations/{var.region}",
                "name": var.name_format % each_value.entry_point,
                "description": "Trigger the Cloud Function",
                "schedule": "*/5  * * * *",
                "httpTarget": {
                    "httpMethod": "POST",
                    "uri": f"$(ref.google_cloudfunctions_function-function-{each_key}.httpsTrigger.url)",
                    "oidcToken": {
                        "serviceAccountEmail": "$(ref.google_service_account-cloud_scheduler.email)",
                    }
                },
            }
        ).as_dict())
    return resources
