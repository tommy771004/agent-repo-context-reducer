const { checkout } = require("../services/order");
async function createOrder(req, res) {
  const result = await checkout(req.body);
  res.json(result);
}
module.exports = { createOrder };
