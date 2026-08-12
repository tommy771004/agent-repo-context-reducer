const { charge } = require("./payment");
async function checkout(input) {
  const payment = await charge(input.total);
  return { status: "paid", payment };
}
module.exports = { checkout };
