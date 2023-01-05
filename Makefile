.PHONY: changelog
changelog:
	git-chglog -o CHANGELOG.md --next-tag `semtag final -s minor -o`

.PHONY: release
release:
	semtag final -s minor
	gcloud storage cp main.py gs://observeinc/deploymentmanager-google-collection-`semtag getcurrent`.py

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
