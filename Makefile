.PHONY: create
create:
	gcloud beta deployment-manager deployments create observe-dm-${USER} \
		--template main.py \
		--properties "resource:'projects/terraflood-345116'"

.PHONY: update
update:
	gcloud beta deployment-manager deployments update observe-dm-${USER} \
		--template main.py \
		--properties "resource:'projects/terraflood-345116'"

.PHONY: delete
delete:
	gcloud beta deployment-manager deployments delete observe-dm-${USER} --quiet

.PHONY: output
output:
	gcloud beta deployment-manager manifests describe --deployment observe-dm-${USER} --format json | jq -r .layout
