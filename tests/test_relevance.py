from utbot.photo_relevance import likely_same_subject

def test_exact_specific_photo_matches():
    assert likely_same_subject('neutron star cosmic hand', {'title':'Cosmic hand around neutron star MSH 15-52'})
    assert likely_same_subject('MSH 15-52', {'title':'MSH1552 from Chandra'})

def test_generic_stock_image_rejected():
    assert not likely_same_subject('cosmic hand neutron star', {'title':'Beautiful random blue galaxy'})
    assert not likely_same_subject('telescope astronomy', {'title':'Telescope image'})

def test_census_page_is_rejected_for_galaxy_radio_story():
    from utbot.photo_relevance import photo_subject_match
    query='radio relic galaxy cluster collision'
    census={'title':'1940 Enumeration Districts Census',
            'description':'historic census archive records mentioning radio galaxy clusters'}
    assert not photo_subject_match(query,census,
        'Radio structure resembling musical note from colliding galaxy clusters')


def test_science_image_must_match_source_topic_too():
    from utbot.photo_relevance import photo_subject_match
    candidate={'title':'Radiation from a galaxy nebula near Mars',
               'description':'Space nebula radiation observation'}
    assert not photo_subject_match('galaxy nebula radiation',candidate,
        'IceCube neutrino detector measures Antarctic events')
    correct={'title':'Galaxy cluster collision radio relic',
             'description':'Radio observations of merging galaxy clusters'}
    assert photo_subject_match('galaxy cluster radio',correct,
        'Radio relic found in collision between galaxy clusters')
