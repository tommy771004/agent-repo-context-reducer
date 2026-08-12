const express = require("express");
const { createOrder } = require("./routes/order");
const app = express();
app.post("/orders", createOrder);
module.exports = { app };
