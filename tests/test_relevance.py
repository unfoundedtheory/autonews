from utbot.photo_relevance import likely_same_subject

def test_exact_specific_photo_matches():
    assert likely_same_subject('neutron star cosmic hand', {'title':'Cosmic hand around neutron star MSH 15-52'})
    assert likely_same_subject('MSH 15-52', {'title':'MSH1552 from Chandra'})

def test_generic_stock_image_rejected():
    assert not likely_same_subject('cosmic hand neutron star', {'title':'Beautiful random blue galaxy'})
    assert not likely_same_subject('telescope astronomy', {'title':'Telescope image'})
