

$(function() {

	/****************************** Index ******************************/
	try {

		var $list = $('.banner-index .list'),
			$btn = $('.banner-index .btn'),
			$ground = $list.clone().addClass('ground'),
			currentIndex = 0,
			bannerVideoPlayer,
			play = function(i) {
			
				clearTimeout(window.autoplayTimer);

				$list.children('li.active').addClass('noscale');
				$list.children('li').eq(i).addClass('active').siblings().removeClass('active');
				$btn.find('a').eq(i).addClass('active').siblings().removeClass('active');

				if (currentIndex >= 0) {
					
					bannerVideoPlayer.currentTime(0);
					bannerVideoPlayer.play();
					setTimeout(function() {
						$list.children('li').removeClass('noscale');

						// 自动播放
						window.autoplayTimer = setTimeout(function() {
							currentIndex++;
							currentIndex = currentIndex >= $list.children('li').length ? 0 : currentIndex;
							play(currentIndex);
						}, 26000);
					}, 2500);
					
				} else if (currentIndex != 0){
					
					bannerVideoPlayer.pause();
				}
				else {
					
					$list.children('li').removeClass('noscale');
					bannerVideoPlayer.play();
				}
			};

		
		$list.before($ground);
		$ground.children('li:not(":last")').remove();

		// 切换按钮
		$btn.find('a').click(function() {
			
			$(this).addClass('active').siblings().removeClass('active')
			currentIndex = $(this).index();
			play(currentIndex);
		});

		bannerVideoPlayer = videojs('banner-video', {
			controls: false,
			autoplay: true
		});

		bannerVideoPlayer.on('ended', function() {
			play(++currentIndex);
		});
	} catch (e) {}

	try {
		if (isMobile) {
			$('.banner-index-mobile').terseBanner({
				adaptive: true,
				init: function($banner, $item) {
					$item.first().addClass('active').addClass('noscale');
				},
				after: function($banner, $item, currentIndex) {
					console.log(currentIndex);
					$item.removeClass('noscale');
					$item.filter('.active').addClass('noscale');
					$item.eq(currentIndex).addClass('active').siblings().removeClass('active');
				},
			});
		}
	} catch (e) {}

	try {
		var divineVideoPlayer = videojs('divine-video', {
			controls: false
		});

		$('.index-marriage .video .play').click(function() {
			$('.index-marriage .video .video-js').show();
			divineVideoPlayer.play();
			divineVideoPlayer.on('ended', function() {
				$('.index-marriage .video .video-js').fadeOut();
			});
		});
	} catch (e) {}


setTimeout(function() {
		$list.children('li').removeClass('noscale');

		// 自动播放
		window.autoplayTimer = setTimeout(function() {
			currentIndex++;
			currentIndex = currentIndex >= $list.children('li').length ? 0 : currentIndex;
			play(currentIndex);
		},26000 );
	}, 2500);


});
