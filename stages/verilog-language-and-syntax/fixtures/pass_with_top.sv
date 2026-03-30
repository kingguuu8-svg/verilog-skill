module helper_leaf(
  input  logic a,
  output logic y
);
  assign y = a;
endmodule

module chosen_top;
  logic sig;
  helper_leaf u_leaf(.a(1'b1), .y(sig));
endmodule

module other_top;
endmodule
