@description('Azure region.')
param location string

@description('Tags applied to the Key Vault.')
param tags object = {}

@minLength(3)
@maxLength(24)
@description('Key Vault name.')
param name string

@description('Object ID granted Key Vault Secrets Officer role. Empty to skip.')
param principalId string = ''

@allowed(['User', 'ServicePrincipal'])
param principalType string = 'User'

resource kv 'Microsoft.KeyVault/vaults@2024-04-01-preview' = {
  name: name
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
  }
}

// Key Vault Secrets Officer
var secretsOfficerRoleId = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  scope: kv
  name: guid(kv.id, principalId, secretsOfficerRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', secretsOfficerRoleId)
    principalId: principalId
    principalType: principalType
  }
}

output name string = kv.name
output uri string = kv.properties.vaultUri
