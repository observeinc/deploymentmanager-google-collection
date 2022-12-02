.PHONY: create
create:
	gcloud beta deployment-manager deployments create observe-dm-${USER} \
		--template main.py \
		--properties "project_id:'terraflood-345116',region:'us-west2',name:'observe-dm-${USER}'"

.PHONY: update
update:
	gcloud beta deployment-manager deployments update observe-collection-dm-${USER} \
		--template main.py \
		--properties "project_id:'terraflood-345116',region:'us-west2',name:'observe-dm-${USER}'"

.PHONY: delete
delete:
	gcloud beta deployment-manager deployments delete observe-collection-dm-${USER} --quiet

.PHONY: output
output:
	gcloud beta deployment-manager manifests describe --deployment observe-collection-dm-${USER}
