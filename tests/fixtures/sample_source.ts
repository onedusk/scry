import { authenticate } from "../shopify.server";

export async function loader({ request }) {
  const { admin } = await authenticate.admin(request);

  const response = await admin.graphql(`#graphql
    query ProductsWithVariants($cursor: String) {
      products(first: 250, after: $cursor) {
        nodes {
          id
          title
          variants(first: 10) {
            nodes { id barcode sku }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  `);

  const mutationResponse = await admin.graphql(`#graphql
    mutation productCreate($input: ProductInput!) {
      productCreate(input: $input) {
        product { id title }
        userErrors { field message }
      }
    }
  `);

  return { products: response, mutation: mutationResponse };
}
