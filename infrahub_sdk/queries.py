def get_commit_update_mutation(is_read_only: bool = False) -> str:
    mutation_commit_update_base = """
    mutation ($repository_id: String!, $commit: String!) {{
        {repo_class}Update(data: {{ id: $repository_id, commit: {{ is_protected: true, source: $repository_id, value: $commit }} }}) {{
            ok
            object {{
                commit {{
                    value
                }}
            }}
        }}
    }}
    """
    if is_read_only:
        return mutation_commit_update_base.format(repo_class="CoreReadOnlyRepository")
    return mutation_commit_update_base.format(repo_class="CoreRepository")


QUERY_RELATIONSHIPS = """
    query GetRelationships($relationship_identifiers: [String!]!) {
        Relationship(ids: $relationship_identifiers) {
            count
            edges {
                node {
                    identifier
                    peers {
                        id
                        kind
                    }
                }
            }
        }
    }
"""

SCHEMA_HASH_SYNC_STATUS = """
query {
  InfrahubStatus {
    summary {
      schema_hash_synced
    }
  }
}
"""

QUERY_USER = """
query GET_PROFILE_DETAILS {
  AccountProfile {
    id
    display_label
    account_type {
      value
      __typename
      updated_at
    }
    status {
      label
      value
      updated_at
      __typename
    }
    description {
      value
      updated_at
      __typename
    }
    label {
      value
      updated_at
      __typename
    }
    member_of_groups {
      count
      edges {
        node {
          display_label
          group_type {
            value
          }
          ... on CoreAccountGroup {
            id
            roles {
              count
              edges {
                node {
                  permissions {
                    count
                    edges {
                      node {
                        display_label
                        identifier {
                          value
                        }
                      }
                    }
                  }
                }
              }
            }
            display_label
          }
        }
      }
    }
    __typename
    name {
      value
      updated_at
      __typename
    }
  }
}
"""
