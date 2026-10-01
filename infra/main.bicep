// Document intelligence lakehouse - core Azure resources.
// Deploy:  az deployment group create -g <rg> -f infra/main.bicep -p infra/main.bicepparam
targetScope = 'resourceGroup'

@description('Short prefix for resource names (lowercase letters/digits).')
@minLength(3)
@maxLength(10)
param prefix string = 'docintel'

@description('Environment name, e.g. dev or prod.')
@allowed(['dev', 'test', 'prod'])
param env string = 'dev'

param location string = resourceGroup().location

@description('Region for Azure OpenAI (model availability differs by region).')
param openAiLocation string = location

@description('Chat model used for structured extraction.')
param openAiModelName string = 'gpt-4o-mini'
param openAiModelVersion string = '2024-07-18'

@description('Deployment capacity in thousands of tokens per minute.')
param openAiCapacity int = 30

@description('Also deploy Azure AI Document Intelligence for OCR of scanned documents.')
param deployDocumentIntelligence bool = true

@description('Optional object id of the service principal that runs the Databricks job (keyless AOAI access).')
param jobServicePrincipalObjectId string = ''

param tags object = {
  project: 'azure-databricks-docintel-lakehouse'
  env: env
}

var suffix = uniqueString(resourceGroup().id, prefix, env)

module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    name: take('${prefix}${env}${suffix}', 24)
    location: location
    tags: tags
  }
}

module databricks 'modules/databricks.bicep' = {
  name: 'databricks'
  params: {
    workspaceName: '${prefix}-${env}-dbw'
    accessConnectorName: '${prefix}-${env}-dbw-ac'
    managedResourceGroupName: '${resourceGroup().name}-${prefix}-${env}-dbw-managed'
    storageAccountName: storage.outputs.name
    location: location
    tags: tags
  }
}

module ai 'modules/ai.bicep' = {
  name: 'ai'
  params: {
    openAiName: '${prefix}-${env}-aoai-${suffix}'
    docIntelName: '${prefix}-${env}-di-${suffix}'
    location: openAiLocation
    modelName: openAiModelName
    modelVersion: openAiModelVersion
    capacity: openAiCapacity
    deployDocumentIntelligence: deployDocumentIntelligence
    callerPrincipalId: jobServicePrincipalObjectId
    tags: tags
  }
}

output storageAccountName string = storage.outputs.name
output landingPath string = 'abfss://landing@${storage.outputs.name}.dfs.${environment().suffixes.storage}/'
output lakehousePath string = 'abfss://lakehouse@${storage.outputs.name}.dfs.${environment().suffixes.storage}/'
output databricksWorkspaceUrl string = databricks.outputs.workspaceUrl
output accessConnectorId string = databricks.outputs.accessConnectorId
output openAiEndpoint string = ai.outputs.openAiEndpoint
output openAiDeployment string = ai.outputs.deploymentName
output documentIntelligenceEndpoint string = ai.outputs.docIntelEndpoint
