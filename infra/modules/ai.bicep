// Azure OpenAI (structured extraction) + optional Azure AI Document Intelligence (OCR).
// The Databricks job reads the API key from a Databricks secret scope. Optionally grant a
// service principal 'Cognitive Services OpenAI User' for Entra ID (keyless) auth instead.
param openAiName string
param docIntelName string
param location string
param modelName string
param modelVersion string
param capacity int
param deployDocumentIntelligence bool
@description('Optional object id of a service principal to grant keyless access.')
param callerPrincipalId string = ''
param tags object

var cognitiveServicesOpenAiUser = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
var cognitiveServicesUser = 'a97b65f3-24c7-4388-baec-2e87135dc908'
var grantCaller = !empty(callerPrincipalId)

resource openai 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: openAiName
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: openAiName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
}

resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openai
  name: modelName
  sku: { name: 'GlobalStandard', capacity: capacity }
  properties: {
    model: { format: 'OpenAI', name: modelName, version: modelVersion }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

resource docintel 'Microsoft.CognitiveServices/accounts@2024-10-01' = if (deployDocumentIntelligence) {
  name: docIntelName
  location: location
  tags: tags
  kind: 'FormRecognizer'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: docIntelName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
}

resource openAiRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (grantCaller) {
  name: guid(openai.id, callerPrincipalId, cognitiveServicesOpenAiUser)
  scope: openai
  properties: {
    principalId: callerPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesOpenAiUser)
  }
}

resource docIntelRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployDocumentIntelligence && grantCaller) {
  name: guid(docIntelName, callerPrincipalId, cognitiveServicesUser)
  scope: docintel
  properties: {
    principalId: callerPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUser)
  }
}

output openAiEndpoint string = openai.properties.endpoint
output deploymentName string = deployment.name
output docIntelEndpoint string = deployDocumentIntelligence ? docintel!.properties.endpoint : ''
