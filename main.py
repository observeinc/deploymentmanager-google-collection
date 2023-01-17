# Allowed imports: see https://cloud.google.com/deployment-manager/docs/configuration/templates/import-python-libraries

import typing
import json


class Variables(object):
    """Variables exists so that Deployment Manager properties (equivalent to Terraform variables) aren't strings."""

    def __init__(self) -> None:
        self.name = ""
        self.resource = ""
        self.labels = {}
        self.pubsub_ack_deadline_seconds = 0
        self.logging_filter = ""
        self.logging_exclusions = []
        self.pubsub_message_retention_duration = ""
        self.pubsub_minimum_backoff = ""
        self.pubsub_maximum_backoff = ""

        self.function_roles = []
        self.enable_function = ""
        self.function_bucket = ""
        self.function_object = ""
        self.function_schedule = ""
        self.function_available_memory_mb = ""
        self.function_timeout = 0
        self.function_max_instances = 0
        self.function_disable_logging = False
        self.poller_roles = []

        self.region = ""


def get_variables(context) -> Variables:
    # context object info:
    # https://cloud.google.com/deployment-manager/docs/configuration/syntax-reference#template_properties
    # https://cloud.google.com/deployment-manager/docs/configuration/syntax-reference#deployment-specific_environment_variables

    var = Variables()

    properties = {}
    if context.properties is not None:
        properties = context.properties

    env = {}
    if context.env is not None:
        env = context.env

    var.name = env["deployment"]
    if not (len(var.name) <= 20):
        raise Exception("The name must be less than 20 characters long.")

    var.resource = properties["resource"]
    if not (len(var.resource.split("/")) == 2):
        raise Exception("The resource value must be formatted as <type>/<id>.")
    if not (var.resource.split("/")[0] in ["projects", "folders", "organizations"]):
        raise Exception(
            "The resource should have prefix 'projects/', 'folders/' or 'organizations/'."
        )

    var.labels = properties.get("labels", {})
    var.pubsub_ack_deadline_seconds = int(
        properties.get("pubsub_ack_deadline_seconds", 60)
    )
    var.logging_filter = properties.get("logging_filter", "")
    var.logging_exclusions = json.loads(properties.get("logging_exclusions", "[]"))
    var.pubsub_message_retention_duration = properties.get(
        "pubsub_message_retention_duration", "86400s"
    )
    var.pubsub_minimum_backoff = properties.get("pubsub_minimum_backoff", "10s")
    var.pubsub_maximum_backoff = properties.get("pubsub_maximum_backoff", "600s")

    var.function_roles = json.loads(
        properties.get(
            "function_roles",
            '["roles/compute.viewer", "roles/iam.serviceAccountViewer", "roles/cloudscheduler.viewer", "roles/cloudasset.viewer", "roles/browser"]',
        )
    )
    enable_function = properties.get("enable_function", "True")
    if enable_function == "True":
        var.enable_function = True
    elif enable_function == "False":
        var.enable_function = False
    else:
        raise Exception("'enable_function' should be 'True' or 'False'")
    var.function_bucket = properties.get("function_bucket", "observeinc")
    var.function_object = properties.get(
        "function_object", "google-cloud-functions-v0.2.0.zip"
    )
    var.function_schedule = properties.get("function_schedule", "*/15 * * * *")
    var.function_available_memory_mb = int(
        properties.get("function_available_memory_mb", "256")
    )
    var.function_timeout = properties.get("function_timeout", "300s")
    var.function_max_instances = int(properties.get("function_max_instances", 5))

    function_disable_logging = properties.get("function_disable_logging", "False")
    if function_disable_logging == "True":
        var.function_disable_logging = True
    elif function_disable_logging == "False":
        var.function_disable_logging = False
    else:
        raise Exception("'function_disable_logging' should be 'True' or 'False'")

    var.poller_roles = json.loads(
        properties.get(
            "poller_roles",
            '["roles/monitoring.viewer"]',
        )
    )

    # deployment manager only
    var.region = properties.get("region", "us-west2")

    return var


class Locals(object):
    def __init__(self, var: Variables, env) -> None:
        # https://cloud.google.com/deployment-manager/docs/configuration/templates/use-environment-variables
        self.project = env["project"]
        self.region = var.region
        self.resource_type = var.resource.split("/")[0]
        self.resource_id = var.resource.split("/")[1]


class Resource:  # See https://cloud.google.com/deployment-manager/docs/configuration/syntax-reference#basic_syntax
    """Resource exists so I don't forget about metadata.dependsOn"""

    def __init__(
        self, name: str, typ: str, properties: dict, metadata=None, accessControl=None
    ) -> None:
        self.name = name
        self.type = typ
        self.properties = properties
        self.metadata = metadata
        self.accessControl = accessControl

    def as_dict(self) -> dict:
        d = {
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }
        if self.metadata is not None:
            d["metadata"] = self.metadata

        if self.accessControl is not None:
            d["accessControl"] = self.accessControl

        return d


def GenerateConfig(context):
    var = get_variables(context)
    local = Locals(var, context.env)

    resources: typing.List[dict] = []

    resources.append(
        Resource(
            "google_pubsub_topic-this",
            # REST API schema: https://cloud.google.com/pubsub/docs/reference/rest/v1/projects.topics
            # Schema override: gcloud beta deployment-manager type-providers describe pubsub-v1 --project gcp-types
            "gcp-types/pubsub-v1:projects.topics",
            {
                "topic": var.name,
                "labels": var.labels,
            },
        ).as_dict()
    )

    resources.append(
        Resource(
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
            },
        ).as_dict()
    )

    # REST API schema: https://cloud.google.com/logging/docs/reference/v2/rest/v2/projects.sinks
    # Schema override: gcloud beta deployment-manager type-providers describe logging-v2 --project gcp-types
    sink_type = f"gcp-types/logging-v2:{local.resource_type}.sinks"

    sink_properties = {
        "sink": var.name,
        "destination": f"pubsub.googleapis.com/$(ref.google_pubsub_topic-this.name)",
        "filter": var.logging_filter,
        "description": "Exports logs to the Observe PubSub topic",
        "exclusions": var.logging_exclusions,
    }
    if local.resource_type == "projects":
        sink_properties["project"] = local.resource_id
    elif local.resource_type == "folders":
        sink_properties["folder"] = local.resource_id
    elif local.resource_type == "organizations":
        sink_properties["organization"] = local.resource_id

    resources.append(
        Resource(
            "google_logging_sink-this",
            sink_type,
            sink_properties,
        ).as_dict()
    )

    resources.append(
        Resource(
            "google_pubsub_topic_iam_member-sink_pubsub",
            # Schema: gcloud beta deployment-manager type-providers describe cloudresourcemanager-v1 --project gcp-types
            "gcp-types/cloudresourcemanager-v1:virtual.projects.iamMemberBinding",
            {
                "resource": local.project,
                "role": "roles/pubsub.publisher",
                "member": "$(ref.google_logging_sink-this.writerIdentity)",
            },
        ).as_dict()
    )

    resources.append(
        Resource(
            "google_service_account-poller",
            # REST API schema: https://cloud.google.com/iam/docs/reference/rest/v1/projects.serviceAccounts
            # Schema override: gcloud beta deployment-manager type-providers describe iam-v1 --project gcp-types
            "gcp-types/iam-v1:projects.serviceAccounts",
            {
                "accountId": f"{var.name}-poll",
                "description": "A service account for the Observe Pub/Sub and Logging pollers",
            },
        ).as_dict()
    )

    for i, each_key in enumerate(var.poller_roles):
        resources.append(
            Resource(
                f"google_project_iam_member-poller-{i}",
                # Schema: gcloud beta deployment-manager type-providers describe cloudresourcemanager-v1 --project gcp-types
                "gcp-types/cloudresourcemanager-v1:virtual.projects.iamMemberBinding",
                {
                    "resource": local.project,
                    "role": each_key,
                    "member": "serviceAccount:$(ref.google_service_account-poller.email)",
                },
            ).as_dict()
        )

    resources.append(
        Resource(
            f"google_pubsub_subscription_iam_member-poller_pubsub",
            # Schema: gcloud beta deployment-manager type-providers describe cloudresourcemanager-v1 --project gcp-types
            "gcp-types/cloudresourcemanager-v1:virtual.projects.iamMemberBinding",
            {
                "resource": local.project,
                "role": "roles/pubsub.subscriber",
                "member": "serviceAccount:$(ref.google_service_account-poller.email)",
            },
        ).as_dict()
    )

    resources.append(
        Resource(
            "google_service_account_key-poller",
            # REST API schema: https://cloud.google.com/iam/docs/reference/rest/v1/projects.serviceAccounts.keys
            # Schema override: gcloud beta deployment-manager type-providers describe iam-v1 --project gcp-types
            "gcp-types/iam-v1:projects.serviceAccounts.keys",
            {"name": "poller", "parent": "$(ref.google_service_account-poller.name)"},
        ).as_dict()
    )

    if var.enable_function:
        resources += function_tf(var, local)

    return {
        "resources": resources,
        "outputs": [
            {
                "name": "project_id",
                "value": local.project,
            },
            {
                "name": "subscription_id",
                "value": var.name,
            },
            {
                "name": "poller_private_key_base64",
                "value": "$(ref.google_service_account_key-poller.privateKeyData)",
            },
        ],
    }


def function_tf(var: Variables, local: Locals) -> typing.List[dict]:
    resources: typing.List[dict] = []
    resources.append(
        Resource(
            "google_service_account-cloudfunction",
            "gcp-types/iam-v1:projects.serviceAccounts",
            {
                "accountId": f"{var.name}-func",
                "description": "Used by the Observe Cloud Functions",
            },
        ).as_dict()
    )

    for each_key in var.function_roles:
        name = f"google_iam_member-cloud_functions-{each_key}"

        # Schema: gcloud beta deployment-manager type-providers describe cloudresourcemanager-v1 --project gcp-types
        # gcloud beta deployment-manager type-providers describe cloudresourcemanager-v2 --project gcp-types
        if local.resource_type == "folders":
            r = var.resource
            type_ = f"gcp-types/cloudresourcemanager-v2:virtual.{local.resource_type}.iamMemberBinding"
        else:
            r = local.resource_id
            type_ = f"gcp-types/cloudresourcemanager-v1:virtual.{local.resource_type}.iamMemberBinding"

        resources.append(
            Resource(
                name,
                type_,
                {
                    "resource": r,
                    "role": each_key,
                    "member": "serviceAccount:$(ref.google_service_account-cloudfunction.email)",
                },
            ).as_dict()
        )

    resources.append(
        Resource(
            "google_pubsub_topic_iam_member-cloudfunction_pubsub",
            # Schema: gcloud beta deployment-manager type-providers describe cloudresourcemanager-v1 --project gcp-types
            "gcp-types/cloudresourcemanager-v1:virtual.projects.iamMemberBinding",
            {
                "resource": local.project,
                "role": "roles/pubsub.publisher",
                "member": "serviceAccount:$(ref.google_service_account-cloudfunction.email)",
            },
        ).as_dict()
    )

    func_env_vars = {
        "PARENT": var.resource,
        "TOPIC_ID": "$(ref.google_pubsub_topic-this.name)",
    }
    if var.function_disable_logging:
        func_env_vars["DISABLE_LOGGING"] = "ok"

    resources.append(
        Resource(
            f"google_cloudfunctions_function-this",
            # Schema: gcloud beta deployment-manager type-providers describe cloudfunctions-v1 --project gcp-types
            "gcp-types/cloudfunctions-v1:projects.locations.functions",
            {
                "function": var.name,
                "parent": f"projects/{local.project}/locations/{local.region}",
                "description": "Polls data from the Google Cloud API and sends to the Observe Pub/Sub topic.",
                "serviceAccountEmail": "$(ref.google_service_account-cloudfunction.email)",
                "runtime": "python310",
                "environmentVariables": func_env_vars,
                "httpsTrigger": {
                    "securityLevel": "SECURE_ALWAYS",
                },
                "ingressSettings": "ALLOW_ALL",
                "availableMemoryMb": var.function_available_memory_mb,
                "timeout": var.function_timeout,
                "maxInstances": var.function_max_instances,
                "sourceArchiveUrl": f"gs://{var.function_bucket}/{var.function_object}",
                "entryPoint": "main",
                "labels": var.labels,
            },
        ).as_dict()
    )

    resources.append(
        Resource(
            "google_service_account-cloud_scheduler",
            "gcp-types/iam-v1:projects.serviceAccounts",
            {
                "accountId": f"{var.name}-sched",
                "description": "A service account to allow the Observe Cloud Scheduler job to trigger some Cloud Functions",
            },
        ).as_dict()
    )

    resources.append(
        Resource(
            "google_cloudfunctions_function_iam_member-cloud_scheduler",
            # Schema: gcloud beta deployment-manager type-providers describe cloudfunctions-v1 --project gcp-types
            "gcp-types/cloudfunctions-v1:virtual.projects.locations.functions.iamMemberBinding",
            {
                "resource": "$(ref.google_cloudfunctions_function-this.name)",
                "role": "roles/cloudfunctions.invoker",
                "member": "serviceAccount:$(ref.google_service_account-cloud_scheduler.email)",
            },
        ).as_dict()
    )

    resources.append(
        Resource(
            f"google_cloud_scheduler_job-this",
            "gcp-types/cloudscheduler-v1:projects.locations.jobs",
            {
                "parent": f"projects/{local.project}/locations/{local.region}",
                "name": var.name,
                "description": "Triggers the Cloud Function",
                "schedule": var.function_schedule,
                "timeZone": "UTC",
                "httpTarget": {
                    "httpMethod": "POST",
                    "uri": f"$(ref.google_cloudfunctions_function-this.httpsTrigger.url)",
                    "oidcToken": {
                        "serviceAccountEmail": "$(ref.google_service_account-cloud_scheduler.email)",
                    },
                },
            },
        ).as_dict()
    )

    return resources
