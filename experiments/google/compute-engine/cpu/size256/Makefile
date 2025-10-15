.PHONY: all
all: init fmt validate deploy

.PHONY: init
init: 
	terraform init
	
.PHONY: fmt
fmt: 
	terraform fmt

.PHONY: validate
validate: 
	terraform validate
	
.PHONY: deploy
deploy: 
	terraform apply -var region=us-central1 -var project_id=llnl-flux -var zone=us-central1-f

.PHONY: destroy
destroy: 
	terraform destroy -var region=us-central1 -var project_id=llnl-flux -var zone=us-central1-f
