export const MOCK_SCHEMA_INTROSPECTION = {
  types: [
    {
      name: 'Query',
      fields: [
        {
          name: 'users',
          type: '[User!]!',
          args: [
            { name: 'first', type: 'Int' },
            { name: 'after', type: 'String' },
            { name: 'orderBy', type: 'UserOrderBy' }
          ]
        },
        {
          name: 'user',
          type: 'User',
          args: [
            { name: 'id', type: 'ID!' }
          ]
        }
      ]
    },
    {
      name: 'User',
      fields: [
        { name: 'id', type: 'ID!' },
        { name: 'name', type: 'String' },
        { name: 'email', type: 'String' },
        { name: 'posts', type: '[Post!]!' }
      ]
    },
    {
      name: 'Post',
      fields: [
        { name: 'id', type: 'ID!' },
        { name: 'title', type: 'String' },
        { name: 'content', type: 'String' },
        { name: 'author', type: 'User' }
      ]
    }
  ]
};

export const MOCK_SCHEMA_FILE = {
  types: [
    {
      name: 'Query',
      fields: [
        {
          name: 'products',
          type: '[Product!]!',
          args: [
            { name: 'category', type: 'String' },
            { name: 'limit', type: 'Int' }
          ]
        },
        {
          name: 'product',
          type: 'Product',
          args: [
            { name: 'id', type: 'ID!' }
          ]
        }
      ]
    },
    {
      name: 'Product',
      fields: [
        { name: 'id', type: 'ID!' },
        { name: 'name', type: 'String' },
        { name: 'price', type: 'Float' },
        { name: 'category', type: 'String' }
      ]
    }
  ]
};

export const MOCK_QUERY = `query UsersWithPosts($first: Int!) {
  users(first: $first) {
    id
    name
    email
    posts {
      id
      title
      content
    }
  }
}`;

export const MOCK_VARIABLES = {
  first: 5
};