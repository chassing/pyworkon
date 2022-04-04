PHONY: github_model

github_model:
	datamodel-codegen --target-python-version 3.9 --url 'https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.yaml' --snake-case-field --use-default --use-standard-collections --openapi-scopes schemas --force-optional  --set-default-enum-member --output pyworkon/providers/github/models.py
