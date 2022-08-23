## Deployment

helm install axies deploy/helm-axies/ --namespace axies --create-namespace --values deploy/local/values.yaml --atomic

helm install deploy/helm-axies/ --namespace axies --create-namespace --values deploy/local/values.yaml --atomic

docker-compose -f deploy/docker-compose.yml up