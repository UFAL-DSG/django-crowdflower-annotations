/*
 * jQuery UI Multi Open Accordion Plugin
 * Author	: Anas Nakawa (http://anasnakawa.wordpress.com/)
 * Date		: 25-01-2011
 * Released Under MIT License
 * You are welcome to enhance this plugin at https://code.google.com/p/jquery-multi-open-accordion/
 */
(function($){
	$.fn.extend({
		//pass the options variable to the function
		multiAccordion: function(options) {
			// TODO: no defaults yet
			var defaults = {
				active: 0
			};
			var options =  $.extend(defaults, options);
			return this.each(function() {
				var $this = $(this);
				var $h3 = $this.children('h3');
				var $div = $this.children('div');
				$this.addClass('ui-accordion ui-widget ui-helper-reset ui-accordion-icons');
				$h3.each(
					function(index){
						var $this = $(this);
						$this.children('a').attr('href', 'javascript:void()');
						$this.addClass('ui-accordion-header ui-helper-reset ui-state-default ui-corner-all').prepend('<span class="ui-icon ui-icon-triangle-1-e"></span>');
						if(isActive(index)) {
							showTab($this)
						} else {
							hideTab($this)
						}
				});
				$this.children('div').each(
					function(index){
						var $this = $(this);
						$this.addClass('ui-accordion-content ui-helper-reset ui-widget-content ui-corner-bottom');
				});
				$h3.click(
					function(){
						var $this = $(this);
						if(!$this.hasClass("ui-state-disabled")) {
							if ($this.hasClass('ui-state-default')) {
								showTab($this);
							} else {
								hideTab($this);
							}
						}
				});
				$h3.hover(
					function() {
						$(this).addClass('ui-state-hover');
					},
					function() {
						$(this).removeClass('ui-state-hover');
					}
				);
			});

			function showTab($this) {
				var $span = $this.children('span.ui-icon');
				var $div = $this.next();
				$this.removeClass('ui-state-default ui-corner-all').addClass('ui-state-active ui-corner-top');
				$span.removeClass('ui-icon-triangle-1-e').addClass('ui-icon-triangle-1-s');
				$div.slideDown('fast', function(){
					$div.addClass('ui-accordion-content-active');
				});
			}

			function hideTab($this) {
				var $span = $this.children('span.ui-icon');
				var $div = $this.next();
				$this.removeClass('ui-state-active ui-corner-top').addClass('ui-state-default ui-corner-all');
				$span.removeClass('ui-icon-triangle-1-s').addClass('ui-icon-triangle-1-e');
				$div.slideUp('fast', function(){
					$div.removeClass('ui-accordion-content-active');
				});
			}

			function isActive(num) {
				// if array
				if(typeof options.active == "boolean" && !options.active) {
					return false;
				} else {
					if(options.active.length !== undefined) {
						for(var i = 0; i < options.active.length; i++) {
							if(options.active[i] == num)
								return true;
						}
					} else {
						return options.active == num;
					}
				}
				return false;
			}
		}
	});
})(jQuery);
