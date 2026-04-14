import api from './api'

export interface Neo4jNode {
  id: number
  labels: string[]
  properties: Record<string, any>
}

export interface Neo4jRelationship {
  source: Neo4jNode
  relationship: {
    type: string
    properties: Record<string, any>
  }
  target: Neo4jNode
}

export interface QueryRequest {
  query: string
  parameters?: Record<string, any>
}

export interface SearchRequest {
  label?: string
  property_key?: string
  property_value?: string
  limit?: number
}

export const neo4jService = {
  /**
   * 获取统计信息
   */
  async getStats() {
    return api.get('/neo4j/stats')
  },

  /**
   * 执行 Cypher 查询
   */
  async executeQuery(request: QueryRequest) {
    return api.post('/neo4j/query', request)
  },

  /**
   * 搜索节点
   */
  async searchNodes(request: SearchRequest) {
    return api.post('/neo4j/search', request)
  },

  /**
   * 获取所有节点
   */
  async getNodes(limit = 100) {
    return api.get('/neo4j/nodes', { params: { limit } })
  },

  /**
   * 根据 ID 获取节点
   */
  async getNodeById(nodeId: number) {
    return api.get(`/neo4j/nodes/${nodeId}`)
  },

  /**
   * 获取所有关系
   */
  async getRelationships(limit = 100) {
    return api.get('/neo4j/relationships', { params: { limit } })
  },

  /**
   * 获取 Neo4j Browser URL
   */
  async getBrowserUrl() {
    return api.get('/neo4j/browser/url')
  },
}
