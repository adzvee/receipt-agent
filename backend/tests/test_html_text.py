from app.email.html_text import html_to_text


def test_keeps_text_and_line_structure():
    html = "<h2>Thanks!</h2><p>Your order</p><div>Total: $13.23</div>"

    assert html_to_text(html) == "Thanks!\nYour order\nTotal: $13.23"


def test_table_cells_stay_on_one_line():
    html = (
        "<table><tr><td>Muffin</td><td>$3.75</td></tr><tr><td>Tax</td><td>$0.98</td></tr></table>"
    )

    assert html_to_text(html) == "Muffin $3.75\nTax $0.98"


def test_drops_scripts_styles_and_head():
    html = (
        "<html><head><title>Receipt</title><style>p{color:red}</style></head>"
        "<body><p>Total $5</p><script>alert('hi')</script></body></html>"
    )

    assert html_to_text(html) == "Total $5"


def test_decodes_entities():
    assert html_to_text("<p>Blue Heron &amp; Co &lt;receipts@example.com&gt;</p>") == (
        "Blue Heron & Co <receipts@example.com>"
    )
