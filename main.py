# Allowed imports: see https://cloud.google.com/deployment-manager/docs/configuration/templates/import-python-libraries

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

    resources = []
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

    # TODO: extensions in terraform-google-collection

    return {
        "resources": resources,
        "outputs": [{
            "name": "subscription_id",
            "value": "$(ref.google_pubsub_subscription-this.name)",
        }, {
            "name": "poller_private_key_base64",
            "value": "$(ref.google_service_account_key-poller.privateKeyData)",
        }]
    }
