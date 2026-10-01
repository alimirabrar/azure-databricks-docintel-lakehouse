// Premium Databricks workspace (required for Unity Catalog) and an access connector
// whose managed identity Unity Catalog uses to reach the ADLS account.
param workspaceName string
param accessConnectorName string
param managedResourceGroupName string
param storageAccountName string
param location string
param tags object

var storageBlobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

resource sa 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource connector 'Microsoft.Databricks/accessConnectors@2024-05-01' = {
  name: accessConnectorName
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {}
}

resource connectorStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(sa.id, connector.id, storageBlobDataContributor)
  scope: sa
  properties: {
    principalId: connector.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributor)
  }
}

resource workspace 'Microsoft.Databricks/workspaces@2024-05-01' = {
  name: workspaceName
  location: location
  tags: tags
  sku: { name: 'premium' }
  properties: {
    managedResourceGroupId: subscriptionResourceId('Microsoft.Resources/resourceGroups', managedResourceGroupName)
    parameters: {
      enableNoPublicIp: { value: true }
    }
  }
}

output workspaceUrl string = 'https://${workspace.properties.workspaceUrl}'
output workspaceId string = workspace.id
output accessConnectorId string = connector.id
output accessConnectorPrincipalId string = connector.identity.principalId
