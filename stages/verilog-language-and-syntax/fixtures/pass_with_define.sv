`ifdef ENABLE_PASS_WITH_DEFINE
module pass_with_define(
  input  logic a,
  output logic y
);
  always_comb begin
    y = a;
  end
endmodule
`else
module pass_with_define_missing_define();
  broken syntax here
endmodule
`endif
